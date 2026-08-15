"""Import preview, dedup, and commit."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
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
from integrations.finance.services.parsers import ParsedTransaction, parse_upload
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


def _tx_to_preview_dict(tx: ParsedTransaction, status: str) -> dict[str, Any]:
    return {
        "date": tx.date.isoformat(),
        "amount_cents": tx.amount_cents,
        "payee": tx.payee,
        "memo": tx.memo,
        "check_number": tx.check_number,
        "fitid": tx.fitid,
        "bank_category": tx.bank_category,
        "dedup_hash": tx.dedup_hash,
        "status": status,
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
            "rows": [],
        }
    existing = _existing_dedup_keys(db, account_id, owner)
    manual_matches = _existing_manual_match_hashes(db, account_id, owner)

    rows: list[dict[str, Any]] = []
    duplicate_count = 0
    possible_manual_duplicate_count = 0
    for tx in parsed:
        # finalize(account_id) is a no-op when the parser already set dedup_hash.
        # That is load-bearing: the same NFCU file can be imported into two accounts.
        tx.finalize(account_id)
        status = "new"
        if tx.fitid and f"fitid:{tx.fitid}" in existing:
            status = "duplicate"
            duplicate_count += 1
        elif tx.dedup_hash in existing:
            status = "duplicate"
            duplicate_count += 1
        else:
            match = movement_match_hash(account_id, tx.date, tx.amount_cents, tx.payee)
            if match in manual_matches:
                status = "possible_manual_duplicate"
                possible_manual_duplicate_count += 1
            existing.add(tx.dedup_hash)
            if tx.fitid:
                existing.add(f"fitid:{tx.fitid}")
        rows.append(_tx_to_preview_dict(tx, status))

    preview_id = str(uuid.uuid4())
    db.add(FinanceImportPreview(
        id=preview_id,
        owner=owner,
        account_id=account_id,
        filename=filename,
        format=fmt,
        payload={"rows": rows},
    ))
    db.commit()

    warning = None
    if (account.purpose or "") == "processor":
        warning = PROCESSOR_WARNING
    return {
        "preview_id": preview_id,
        "format": fmt,
        "row_count": len(rows),
        "new_count": len(rows) - duplicate_count,
        "duplicate_count": duplicate_count,
        "possible_manual_duplicate_count": possible_manual_duplicate_count,
        "error_count": len(parse_errors),
        "errors": [{"row": e.row, "message": e.message} for e in parse_errors],
        "rows": rows,
        "needs_mapping": False,
        "warning": warning,
    }


def commit_import_preview(
    db: Session,
    owner: str,
    preview_id: str,
    skip_duplicates: bool = True,
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
    for row in rows:
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
        "movements_auto_linked": len(movements.get("auto_linked") or []),
        "movements_suggestions": len(movements.get("suggestions") or []),
        "unmatched_funding": len(movements.get("unmatched_funding") or []),
        "warning": warning,
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
