"""Import preview, dedup, and commit."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from integrations.finance.models import (
    FinanceAccount,
    FinanceImportBatch,
    FinanceImportPreview,
    FinanceTransaction,
    utcnow_naive,
)
from integrations.finance.services.categories import apply_rules_to_transactions
from integrations.finance.services.parsers import ParsedTransaction, parse_upload, _normalize_payee
from integrations.finance.services.transactions import movement_match_hash


PREVIEW_TTL_HOURS = 2


def _utcnow() -> datetime:
    return utcnow_naive()


def cleanup_stale_previews(db: Session, owner: str) -> None:
    cutoff = _utcnow() - timedelta(hours=PREVIEW_TTL_HOURS)
    db.query(FinanceImportPreview).filter(
        FinanceImportPreview.owner == owner,
        FinanceImportPreview.created_at < cutoff,
    ).delete(synchronize_session=False)
    db.commit()


def _existing_dedup_keys(db: Session, account_id: str, owner: str) -> set[str]:
    rows = (
        db.query(FinanceTransaction.dedup_hash, FinanceTransaction.fitid)
        .filter(
            FinanceTransaction.account_id == account_id,
            FinanceTransaction.owner == owner,
        )
        .all()
    )
    keys: set[str] = set()
    for dedup_hash, fitid in rows:
        keys.add(dedup_hash)
        if fitid:
            keys.add(f"fitid:{fitid}")
    return keys


def _existing_manual_match_hashes(db: Session, account_id: str, owner: str) -> set[str]:
    rows = (
        db.query(FinanceTransaction.match_hash)
        .filter(
            FinanceTransaction.account_id == account_id,
            FinanceTransaction.owner == owner,
            FinanceTransaction.source == "manual",
            FinanceTransaction.match_hash.isnot(None),
        )
        .all()
    )
    return {row[0] for row in rows if row[0]}


def _existing_rows(db: Session, account_id: str, owner: str) -> list[FinanceTransaction]:
    return (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.account_id == account_id,
            FinanceTransaction.owner == owner,
        )
        .all()
    )


def _payees_close(left: str, right: str) -> bool:
    a = _normalize_payee(left)
    b = _normalize_payee(right)
    if not a or not b:
        return True
    if a == b:
        return True
    return a in b or b in a


def _iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)[:10]


def _enrich_fields(existing: FinanceTransaction, incoming: ParsedTransaction) -> dict[str, Any]:
    """Fields to copy onto an existing row. Never overwrites a value that is already set."""
    patch: dict[str, Any] = {}
    if existing.daily_balance_cents is None and incoming.daily_balance_cents is not None:
        patch["daily_balance_cents"] = incoming.daily_balance_cents
    if existing.statement_start is None and incoming.statement_start is not None:
        patch["statement_start"] = incoming.statement_start.isoformat()
    if existing.statement_end is None and incoming.statement_end is not None:
        patch["statement_end"] = incoming.statement_end.isoformat()
    if not (existing.source_statement or "").strip() and incoming.source_statement:
        patch["source_statement"] = incoming.source_statement[:500]
    if not (existing.check_number or "").strip() and incoming.check_number:
        patch["check_number"] = incoming.check_number
    if not (existing.memo or "").strip() and incoming.memo:
        patch["memo"] = incoming.memo[:1000]
    incoming_payee = (incoming.payee or "").strip()
    existing_payee = (existing.payee or "").strip()
    if incoming_payee:
        if not existing_payee:
            patch["payee"] = incoming_payee[:500]
        else:
            old_key = _normalize_payee(existing_payee)
            new_key = _normalize_payee(incoming_payee)
            if old_key != new_key and old_key in new_key and len(new_key) > len(old_key):
                patch["payee"] = incoming_payee[:500]
    return patch


def _find_existing_match(
    tx: ParsedTransaction,
    *,
    by_hash: dict[str, FinanceTransaction],
    by_fitid: dict[str, FinanceTransaction],
    by_date_amount: dict[tuple, list[FinanceTransaction]],
    claimed: set[str],
) -> FinanceTransaction | None:
    if tx.fitid:
        hit = by_fitid.get(tx.fitid)
        if hit and hit.id not in claimed:
            return hit
    hit = by_hash.get(tx.dedup_hash)
    if hit and hit.id not in claimed:
        return hit
    candidates = [
        row
        for row in by_date_amount.get((tx.date, tx.amount_cents), [])
        if row.id not in claimed and (row.source or "import") != "manual"
    ]
    if not candidates:
        return None
    equal = [
        row for row in candidates if _normalize_payee(row.payee) == _normalize_payee(tx.payee)
    ]
    if equal:
        return equal[0]
    close = [row for row in candidates if _payees_close(row.payee, tx.payee)]
    if close:
        return close[0]
    return None


def _apply_enrich_row(existing: FinanceTransaction, enrich: dict[str, Any]) -> bool:
    from integrations.finance.services.accounts import parse_optional_date

    changed = False
    if existing.daily_balance_cents is None and enrich.get("daily_balance_cents") is not None:
        existing.daily_balance_cents = int(enrich["daily_balance_cents"])
        changed = True
    if existing.statement_start is None and enrich.get("statement_start"):
        existing.statement_start = parse_optional_date(enrich["statement_start"])
        changed = True
    if existing.statement_end is None and enrich.get("statement_end"):
        existing.statement_end = parse_optional_date(enrich["statement_end"])
        changed = True
    if not (existing.source_statement or "").strip() and enrich.get("source_statement"):
        existing.source_statement = str(enrich["source_statement"])[:500]
        changed = True
    if not (existing.check_number or "").strip() and enrich.get("check_number"):
        existing.check_number = str(enrich["check_number"])
        changed = True
    if not (existing.memo or "").strip() and enrich.get("memo"):
        existing.memo = str(enrich["memo"])[:1000]
        changed = True
    new_payee = (enrich.get("payee") or "").strip()
    if new_payee:
        old = (existing.payee or "").strip()
        if not old:
            existing.payee = new_payee[:500]
            changed = True
        else:
            old_key = _normalize_payee(old)
            new_key = _normalize_payee(new_payee)
            if old_key != new_key and old_key in new_key and len(new_key) > len(old_key):
                existing.payee = new_payee[:500]
                changed = True
    return changed


def _tx_to_preview_dict(
    tx: ParsedTransaction,
    status: str,
    *,
    existing_id: str | None = None,
    enrich: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "date": tx.date.isoformat(),
        "amount_cents": tx.amount_cents,
        "payee": tx.payee,
        "memo": tx.memo,
        "check_number": tx.check_number,
        "fitid": tx.fitid,
        "bank_category": tx.bank_category,
        "dedup_hash": tx.dedup_hash,
        "daily_balance_cents": tx.daily_balance_cents,
        "statement_start": _iso(tx.statement_start),
        "statement_end": _iso(tx.statement_end),
        "source_statement": tx.source_statement,
        "status": status,
        "existing_id": existing_id,
        "enrich": enrich or {},
    }


PROCESSOR_WARNING = (
    "Processor CSV imported unpaired. Unpaired class is valid; classify funding legs when the counterpart book exists."
)


def build_import_preview(
    db: Session,
    owner: str,
    account_id: str,
    filename: str,
    content: bytes,
    preset: str | None = None,
    mapping: dict | None = None,
    options: dict | None = None,
    mapping_id: str | None = None,
) -> dict[str, Any]:
    account = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    if not account:
        raise ValueError("Account not found")

    cleanup_stale_previews(db, owner)
    from integrations.finance.services.mappings import (
        fingerprint_headers,
        get_mapping_by_fingerprint,
        get_mapping_by_id,
    )
    from integrations.finance.services.parsers import _read_csv_dicts, detect_file_format

    if mapping_id and not mapping:
        saved = get_mapping_by_id(db, owner, mapping_id)
        if saved:
            mapping = saved.mapping
            options = options or saved.options
    if not mapping:
        fmt_guess = detect_file_format(filename, content)
        if fmt_guess != "ofx":
            try:
                headers = list(_read_csv_dicts(content.decode("utf-8", errors="replace"))[0].keys())
            except (ValueError, IndexError):
                headers = []
            saved = get_mapping_by_fingerprint(db, owner, fingerprint_headers(headers)) if headers else None
            if saved:
                mapping = saved.mapping
                options = options or saved.options
    fmt, parsed, parse_errors, extra = parse_upload(
        filename, content, preset, mapping=mapping, options=options
    )
    if extra.get("needs_mapping"):
        return {
            "needs_mapping": True,
            "format": fmt,
            "columns": extra.get("columns") or [],
            "suggested_mapping": extra.get("suggested_mapping") or {},
            "fingerprint": fingerprint_headers(extra.get("columns") or []),
            "preview_id": None,
            "new_count": 0,
            "duplicate_count": 0,
            "enrich_count": 0,
            "rows": [],
        }
    stored = _existing_rows(db, account_id, owner)
    by_hash: dict[str, FinanceTransaction] = {}
    by_fitid: dict[str, FinanceTransaction] = {}
    by_date_amount: dict[tuple, list[FinanceTransaction]] = defaultdict(list)
    for row in stored:
        by_hash[row.dedup_hash] = row
        if row.fitid:
            by_fitid[row.fitid] = row
        by_date_amount[(row.date, row.amount_cents)].append(row)
    manual_matches = _existing_manual_match_hashes(db, account_id, owner)

    rows: list[dict[str, Any]] = []
    duplicate_count = 0
    enrich_count = 0
    possible_manual_duplicate_count = 0
    claimed: set[str] = set()
    seen_hashes: set[str] = set()
    for tx in parsed:
        # finalize(account_id) is a no-op when the parser already set dedup_hash.
        # That is load-bearing: the same NFCU file can be imported into two accounts.
        tx.finalize(account_id)
        if tx.dedup_hash in seen_hashes:
            duplicate_count += 1
            rows.append(_tx_to_preview_dict(tx, "duplicate"))
            continue
        seen_hashes.add(tx.dedup_hash)
        match = _find_existing_match(
            tx,
            by_hash=by_hash,
            by_fitid=by_fitid,
            by_date_amount=by_date_amount,
            claimed=claimed,
        )
        if match:
            claimed.add(match.id)
            patch = _enrich_fields(match, tx)
            if patch:
                enrich_count += 1
                rows.append(
                    _tx_to_preview_dict(tx, "enrich", existing_id=match.id, enrich=patch)
                )
            else:
                duplicate_count += 1
                rows.append(_tx_to_preview_dict(tx, "duplicate", existing_id=match.id))
            continue
        status = "new"
        manual_key = movement_match_hash(account_id, tx.date, tx.amount_cents, tx.payee)
        if manual_key in manual_matches:
            status = "possible_manual_duplicate"
            possible_manual_duplicate_count += 1
        rows.append(_tx_to_preview_dict(tx, status))

    preview_id = str(uuid.uuid4())
    warning = None
    if (account.purpose or "") == "processor":
        warning = PROCESSOR_WARNING
    opening = None
    opening_cents = extra.get("opening_posted_cents")
    opening_as_of = extra.get("opening_as_of")
    if opening_cents is not None and opening_as_of:
        opening = {
            "opening_posted_cents": int(opening_cents),
            "opening_as_of": opening_as_of,
            "account_has_opening": bool(account.opening_balance_date),
        }
    db.add(FinanceImportPreview(
        id=preview_id,
        owner=owner,
        account_id=account_id,
        filename=filename,
        format=fmt,
        payload={"rows": rows, "opening": opening},
    ))
    db.commit()
    return {
        "preview_id": preview_id,
        "format": fmt,
        "row_count": len(rows),
        "new_count": len(rows) - duplicate_count - enrich_count,
        "duplicate_count": duplicate_count,
        "enrich_count": enrich_count,
        "possible_manual_duplicate_count": possible_manual_duplicate_count,
        "error_count": len(parse_errors),
        "errors": [{"row": e.row, "message": e.message} for e in parse_errors],
        "rows": rows,
        "needs_mapping": False,
        "warning": warning,
        "opening": opening,
    }


def commit_import_preview(
    db: Session,
    owner: str,
    preview_id: str,
    skip_duplicates: bool = True,
    apply_opening: bool = False,
) -> dict[str, Any]:
    preview = (
        db.query(FinanceImportPreview)
        .filter(FinanceImportPreview.id == preview_id, FinanceImportPreview.owner == owner)
        .first()
    )
    if not preview:
        raise ValueError("Import preview not found or expired")
    if not preview.account_id:
        raise ValueError("Preview missing account")

    account_id = preview.account_id
    rows = (preview.payload or {}).get("rows") or []
    existing = _existing_dedup_keys(db, account_id, owner)

    batch = FinanceImportBatch(
        id=str(uuid.uuid4()),
        owner=owner,
        account_id=account_id,
        filename=preview.filename or "",
        format=preview.format or "csv_generic",
        row_count=len(rows),
    )
    db.add(batch)

    imported: list[FinanceTransaction] = []
    duplicate_count = 0
    enriched_count = 0
    from integrations.finance.services.accounts import parse_optional_date

    for row in rows:
        existing_id = row.get("existing_id")
        if existing_id:
            existing_tx = (
                db.query(FinanceTransaction)
                .filter(
                    FinanceTransaction.id == existing_id,
                    FinanceTransaction.account_id == account_id,
                    FinanceTransaction.owner == owner,
                )
                .first()
            )
            if existing_tx and _apply_enrich_row(existing_tx, row.get("enrich") or {}):
                enriched_count += 1
            else:
                duplicate_count += 1
            continue
        if skip_duplicates and row.get("status") == "duplicate":
            duplicate_count += 1
            continue
        dedup_hash = row.get("dedup_hash") or ""
        fitid = row.get("fitid")
        if fitid and f"fitid:{fitid}" in existing:
            duplicate_count += 1
            continue
        if dedup_hash in existing:
            duplicate_count += 1
            continue

        tx = FinanceTransaction(
            id=str(uuid.uuid4()),
            owner=owner,
            account_id=account_id,
            import_batch_id=batch.id,
            date=datetime.strptime(row["date"], "%Y-%m-%d").date(),
            amount_cents=int(row["amount_cents"]),
            payee=(row.get("payee") or "")[:500],
            memo=(row.get("memo") or "")[:1000],
            check_number=row.get("check_number"),
            fitid=fitid,
            dedup_hash=dedup_hash,
            bank_category=row.get("bank_category"),
            status="cleared",
            source="import",
            daily_balance_cents=row.get("daily_balance_cents"),
            statement_start=parse_optional_date(row.get("statement_start")),
            statement_end=parse_optional_date(row.get("statement_end")),
            source_statement=(row.get("source_statement") or None),
        )
        nested = db.begin_nested()
        try:
            db.add(tx)
            db.flush()
        except IntegrityError:
            nested.rollback()
            duplicate_count += 1
            continue
        imported.append(tx)
        existing.add(dedup_hash)
        if fitid:
            existing.add(f"fitid:{fitid}")

    apply_rules_to_transactions(db, owner, imported)
    batch.imported_count = len(imported)
    batch.duplicate_count = duplicate_count

    opening_applied = False
    opening = (preview.payload or {}).get("opening") or {}
    if (
        apply_opening
        and opening.get("opening_posted_cents") is not None
        and opening.get("opening_as_of")
    ):
        from integrations.finance.services.accounts import parse_optional_date

        account_row = (
            db.query(FinanceAccount)
            .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
            .first()
        )
        if account_row:
            account_row.opening_balance_cents = int(opening["opening_posted_cents"])
            account_row.opening_balance_date = parse_optional_date(opening["opening_as_of"])
            opening_applied = True

    db.delete(preview)
    db.commit()

    from integrations.finance.services.movements import detect_movements

    movements = detect_movements(db, owner, auto_link=True)
    account = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    warning = PROCESSOR_WARNING if account and (account.purpose or "") == "processor" else None
    return {
        "batch_id": batch.id,
        "imported_count": len(imported),
        "duplicate_count": duplicate_count,
        "enriched_count": enriched_count,
        "movements_auto_linked": len(movements.get("auto_linked") or []),
        "movements_suggestions": len(movements.get("suggestions") or []),
        "unmatched_funding": len(movements.get("unmatched_funding") or []),
        "warning": warning,
        "opening_applied": opening_applied,
    }


def rollback_import_batch(db: Session, owner: str, batch_id: str) -> int:
    from integrations.finance.services.movements import cleanup_orphaned_movement_groups
    from integrations.finance.services.transactions import delete_splits_for_transactions

    batch = (
        db.query(FinanceImportBatch)
        .filter(FinanceImportBatch.id == batch_id, FinanceImportBatch.owner == owner)
        .first()
    )
    if not batch:
        raise ValueError("Import batch not found")
    txs = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.import_batch_id == batch_id,
            FinanceTransaction.owner == owner,
        )
        .all()
    )
    group_ids = {tx.movement_group_id for tx in txs if tx.movement_group_id}
    tx_ids = [tx.id for tx in txs]
    delete_splits_for_transactions(db, owner, tx_ids)
    deleted = (
        db.query(FinanceTransaction)
        .filter(
            FinanceTransaction.import_batch_id == batch_id,
            FinanceTransaction.owner == owner,
        )
        .delete(synchronize_session=False)
    )
    cleanup_orphaned_movement_groups(db, owner, group_ids)
    db.delete(batch)
    db.commit()
    return int(deleted)
