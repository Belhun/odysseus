"""Transaction query filters and ledger CRUD."""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, exists, or_
from sqlalchemy.orm import Query, Session

from integrations.finance.models import (
    MOVEMENT_CLASSES,
    TX_STATUSES,
    FinanceAccount,
    FinanceTransaction,
    FinanceTransactionSplit,
)
from integrations.finance.services.accounts import log_mutation
from integrations.finance.services.balances import normalize_tx_status
from integrations.finance.services.parsers import _normalize_payee


class ImportedTransactionError(ValueError):
    """Raised when a hard-delete is attempted on an imported row."""


def parse_optional_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    return datetime.strptime(raw[:10], "%Y-%m-%d").date()


def validate_status(status: str | None) -> str:
    value = normalize_tx_status(status)
    if value not in TX_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(TX_STATUSES)}")
    return value


def validate_movement_class(movement_class: str | None, *, allow_null: bool = True) -> str | None:
    if movement_class is None or movement_class == "":
        if allow_null:
            return None
        raise ValueError("movement_class is required")
    value = str(movement_class).strip().lower()
    if value not in MOVEMENT_CLASSES:
        raise ValueError(f"movement_class must be one of: {', '.join(MOVEMENT_CLASSES)}")
    return value


def _owned_account(db: Session, owner: str, account_id: str) -> FinanceAccount:
    account = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    if not account:
        raise ValueError("Account not found")
    if account.is_closed:
        raise ValueError("Account is closed")
    return account


def _owned_tx(db: Session, owner: str, tx_id: str) -> FinanceTransaction:
    tx = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.id == tx_id, FinanceTransaction.owner == owner)
        .first()
    )
    if not tx:
        raise ValueError("Transaction not found")
    return tx


def apply_transaction_filters(
    q: Query,
    *,
    owner: str,
    account_id: Optional[str] = None,
    category_id: Optional[str] = None,
    month: Optional[str] = None,
    search: str = "",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    min_amount_cents: Optional[int] = None,
    max_amount_cents: Optional[int] = None,
    uncategorized: bool = False,
    movement_class: Optional[str] = None,
    unclassified: bool = False,
    include_void: bool = False,
    status: Optional[str] = None,
) -> Query:
    q = q.filter(FinanceTransaction.owner == owner)
    if account_id:
        account_ref = str(account_id).strip()
        q = q.filter(FinanceTransaction.account_id.startswith(account_ref))
    if category_id:
        split_in_category = exists().where(
            and_(
                FinanceTransactionSplit.transaction_id == FinanceTransaction.id,
                FinanceTransactionSplit.owner == owner,
                FinanceTransactionSplit.category_id == category_id,
            )
        )
        q = q.filter(
            or_(
                FinanceTransaction.category_id == category_id,
                split_in_category,
            )
        )
    if month:
        from integrations.finance.services.reports import month_bounds

        start, end = month_bounds(month)
        q = q.filter(FinanceTransaction.date >= start, FinanceTransaction.date <= end)
    if start_date:
        q = q.filter(FinanceTransaction.date >= parse_optional_date(start_date))
    if end_date:
        q = q.filter(FinanceTransaction.date <= parse_optional_date(end_date))
    if min_amount_cents is not None:
        q = q.filter(FinanceTransaction.amount_cents >= int(min_amount_cents))
    if max_amount_cents is not None:
        q = q.filter(FinanceTransaction.amount_cents <= int(max_amount_cents))
    if uncategorized:
        q = q.filter(FinanceTransaction.category_id.is_(None))
    if unclassified:
        q = q.filter(FinanceTransaction.movement_class.is_(None))
    if movement_class:
        q = q.filter(FinanceTransaction.movement_class == validate_movement_class(movement_class))
    if status:
        q = q.filter(FinanceTransaction.status == validate_status(status))
    elif not include_void:
        q = q.filter(
            (FinanceTransaction.status.is_(None))
            | (FinanceTransaction.status != "void")
        )
    if search.strip():
        like = f"%{search.strip()}%"
        q = q.filter(FinanceTransaction.payee.ilike(like))
    return q


def _manual_dedup_hash(account_id: str, tx_date: date, amount_cents: int, payee: str, tx_id: str) -> str:
    key = "|".join([
        account_id,
        tx_date.isoformat(),
        str(amount_cents),
        _normalize_payee(payee),
        "manual",
        tx_id,
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def movement_match_hash(account_id: str, tx_date: date, amount_cents: int, payee: str) -> str:
    """Unsalted identity hash used to flag a bank row that matches a manual entry."""
    key = "|".join([
        account_id,
        tx_date.isoformat(),
        str(amount_cents),
        _normalize_payee(payee),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def delete_splits_for_transactions(db: Session, owner: str, tx_ids: list[str]) -> int:
    if not tx_ids:
        return 0
    return (
        db.query(FinanceTransactionSplit)
        .filter(
            FinanceTransactionSplit.owner == owner,
            FinanceTransactionSplit.transaction_id.in_(tx_ids),
        )
        .delete(synchronize_session=False)
    )


def _tx_snapshot(tx: FinanceTransaction) -> dict:
    return {
        "id": tx.id,
        "account_id": tx.account_id,
        "date": tx.date.isoformat() if tx.date else None,
        "amount_cents": tx.amount_cents,
        "payee": tx.payee,
        "memo": tx.memo,
        "status": tx.status,
        "source": tx.source,
        "category_id": tx.category_id,
        "movement_class": tx.movement_class,
        "movement_group_id": tx.movement_group_id,
    }


def create_manual_transaction(
    db: Session,
    owner: str,
    *,
    account_id: str,
    date_raw: str,
    amount_cents: int,
    payee: str = "",
    memo: str = "",
    category_id: Optional[str] = None,
    status: str = "cleared",
    movement_class: Optional[str] = None,
    actor: str = "user",
) -> FinanceTransaction:
    account = _owned_account(db, owner, account_id)
    tx_date = parse_optional_date(date_raw)
    if not tx_date:
        raise ValueError("date is required")
    tx_id = str(uuid.uuid4())
    tx = FinanceTransaction(
        id=tx_id,
        owner=owner,
        account_id=account.id,
        date=tx_date,
        amount_cents=int(amount_cents),
        payee=(payee or "")[:500],
        memo=(memo or "")[:1000],
        category_id=category_id,
        status=validate_status(status),
        source="manual",
        movement_class=validate_movement_class(movement_class),
        dedup_hash=_manual_dedup_hash(account.id, tx_date, int(amount_cents), payee or "", tx_id),
        match_hash=movement_match_hash(account.id, tx_date, int(amount_cents), payee or ""),
    )
    db.add(tx)
    log_mutation(
        db,
        owner,
        action="create",
        entity_type="transaction",
        entity_id=tx.id,
        after=_tx_snapshot(tx),
        actor=actor,
    )
    db.commit()
    return tx


def patch_ledger_transaction(
    db: Session,
    owner: str,
    tx_id: str,
    *,
    amount_cents: Optional[int] = None,
    date_raw: Optional[str] = None,
    account_id: Optional[str] = None,
    payee: Optional[str] = None,
    memo: Optional[str] = None,
    category_id: Optional[str] = None,
    status: Optional[str] = None,
    movement_class: Optional[str] = None,
    actor: str = "user",
) -> FinanceTransaction:
    tx = _owned_tx(db, owner, tx_id)
    before = _tx_snapshot(tx)
    ledger_changed = False
    if account_id is not None and account_id != tx.account_id:
        _owned_account(db, owner, account_id)
        tx.account_id = account_id
        ledger_changed = True
    if date_raw is not None:
        next_date = parse_optional_date(date_raw)
        if not next_date:
            raise ValueError("date is required")
        tx.date = next_date
        ledger_changed = True
    if amount_cents is not None:
        tx.amount_cents = int(amount_cents)
        ledger_changed = True
    if payee is not None:
        tx.payee = payee[:500]
    if memo is not None:
        tx.memo = memo[:1000]
    if category_id is not None:
        tx.category_id = category_id or None
    if status is not None:
        tx.status = validate_status(status)
        ledger_changed = True
    if movement_class is not None:
        tx.movement_class = validate_movement_class(movement_class)
    if category_id is not None:
        from integrations.finance.services.movements import maybe_class_from_transfers_category

        maybe_class_from_transfers_category(db, owner, tx)
    if tx.source == "manual":
        tx.dedup_hash = _manual_dedup_hash(
            tx.account_id, tx.date, tx.amount_cents, tx.payee or "", tx.id
        )
        tx.match_hash = movement_match_hash(
            tx.account_id, tx.date, tx.amount_cents, tx.payee or ""
        )
    if ledger_changed or movement_class is not None or payee is not None or memo is not None or category_id is not None:
        log_mutation(
            db,
            owner,
            action="patch",
            entity_type="transaction",
            entity_id=tx.id,
            before=before,
            after=_tx_snapshot(tx),
            actor=actor,
        )
    db.commit()
    return tx


def void_transaction(
    db: Session,
    owner: str,
    tx_id: str,
    *,
    actor: str = "user",
) -> FinanceTransaction:
    tx = _owned_tx(db, owner, tx_id)
    if normalize_tx_status(tx.status) == "void":
        return tx
    before = _tx_snapshot(tx)
    tx.status = "void"
    log_mutation(
        db,
        owner,
        action="void",
        entity_type="transaction",
        entity_id=tx.id,
        before=before,
        after=_tx_snapshot(tx),
        actor=actor,
    )
    db.commit()
    return tx


def unvoid_transaction(
    db: Session,
    owner: str,
    tx_id: str,
    *,
    actor: str = "user",
) -> FinanceTransaction:
    tx = _owned_tx(db, owner, tx_id)
    if normalize_tx_status(tx.status) != "void":
        return tx
    before = _tx_snapshot(tx)
    tx.status = "cleared"
    log_mutation(
        db,
        owner,
        action="unvoid",
        entity_type="transaction",
        entity_id=tx.id,
        before=before,
        after=_tx_snapshot(tx),
        actor=actor,
    )
    db.commit()
    return tx


def delete_manual_transaction(
    db: Session,
    owner: str,
    tx_id: str,
    *,
    actor: str = "user",
) -> None:
    tx = _owned_tx(db, owner, tx_id)
    is_imported = bool(tx.import_batch_id) or (tx.source or "import") == "import"
    if is_imported:
        raise ImportedTransactionError(
            "Imported transactions cannot be deleted; void them or roll back the import batch"
        )
    before = _tx_snapshot(tx)
    log_mutation(
        db,
        owner,
        action="delete",
        entity_type="transaction",
        entity_id=tx.id,
        before=before,
        actor=actor,
    )
    delete_splits_for_transactions(db, owner, [tx.id])
    db.delete(tx)
    db.commit()


def set_transaction_splits(
    db: Session,
    owner: str,
    transaction_id: str,
    splits: list[dict],
) -> list:
    """Replace splits for a transaction; splits must sum to parent amount."""
    from integrations.finance.models import FinanceTransactionSplit

    tx = _owned_tx(db, owner, transaction_id)
    if not splits:
        raise ValueError("At least one split is required")

    total = sum(int(s.get("amount_cents") or 0) for s in splits)
    if total != tx.amount_cents:
        raise ValueError(
            f"Split amounts ({total}) must equal transaction amount ({tx.amount_cents})"
        )

    db.query(FinanceTransactionSplit).filter(
        FinanceTransactionSplit.transaction_id == transaction_id,
        FinanceTransactionSplit.owner == owner,
    ).delete(synchronize_session=False)

    created = []
    for entry in splits:
        split = FinanceTransactionSplit(
            id=str(uuid.uuid4()),
            owner=owner,
            transaction_id=transaction_id,
            category_id=entry.get("category_id"),
            amount_cents=int(entry["amount_cents"]),
            memo=(entry.get("memo") or "")[:500],
        )
        db.add(split)
        created.append(split)

    tx.category_id = None
    db.commit()
    return created
