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


def build_import_preview(
    db: Session,
    owner: str,
    account_id: str,
    filename: str,
    content: bytes,
    preset: str | None = None,
) -> dict[str, Any]:
    account = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    if not account:
        raise ValueError("Account not found")

    cleanup_stale_previews(db, owner)
    fmt, parsed, parse_errors = parse_upload(filename, content, preset)
    existing = _existing_dedup_keys(db, account_id, owner)

    rows: list[dict[str, Any]] = []
    duplicate_count = 0
    for tx in parsed:
        tx.finalize(account_id)
        status = "new"
        if tx.fitid and f"fitid:{tx.fitid}" in existing:
            status = "duplicate"
            duplicate_count += 1
        elif tx.dedup_hash in existing:
            status = "duplicate"
            duplicate_count += 1
        else:
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

    return {
        "preview_id": preview_id,
        "format": fmt,
        "row_count": len(rows),
        "new_count": len(rows) - duplicate_count,
        "duplicate_count": duplicate_count,
        "error_count": len(parse_errors),
        "errors": [{"row": e.row, "message": e.message} for e in parse_errors],
        "rows": rows,
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

    return {
        "batch_id": batch.id,
        "imported_count": len(imported),
        "duplicate_count": duplicate_count,
    }


from integrations.finance.services.balances import posted_cents as account_balance_cents
