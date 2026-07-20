"""Account CRUD for the Finance plugin."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from integrations.finance.models import FinanceAccount, FinanceTransaction
from integrations.finance.services.import_service import account_balance_cents

ACCOUNT_TYPES = ("checking", "savings", "credit_card", "loan", "cash", "other")


def parse_optional_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    return datetime.strptime(raw[:10], "%Y-%m-%d").date()


def account_dict(db: Session, account: FinanceAccount) -> dict[str, Any]:
    balance = account_balance_cents(db, account)
    return {
        "id": account.id,
        "name": account.name,
        "institution": account.institution or "",
        "account_type": account.account_type,
        "currency": account.currency,
        "mask_last4": account.mask_last4,
        "opening_balance_cents": account.opening_balance_cents or 0,
        "opening_balance_date": account.opening_balance_date.isoformat() if account.opening_balance_date else None,
        "credit_limit_cents": account.credit_limit_cents,
        "is_closed": bool(account.is_closed),
        "display_order": account.display_order or 0,
        "balance_cents": balance,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def list_accounts_for_owner(
    db: Session,
    owner: str,
    *,
    include_closed: bool = False,
) -> list[FinanceAccount]:
    q = db.query(FinanceAccount).filter(FinanceAccount.owner == owner)
    if not include_closed:
        q = q.filter(FinanceAccount.is_closed == False)  # noqa: E712
    return q.order_by(FinanceAccount.display_order, FinanceAccount.name).all()


def create_account_for_owner(
    db: Session,
    owner: str,
    *,
    name: str,
    institution: str = "",
    account_type: str = "checking",
    currency: str = "USD",
    mask_last4: Optional[str] = None,
    opening_balance_cents: int = 0,
    opening_balance_date: Optional[str] = None,
    credit_limit_cents: Optional[int] = None,
) -> FinanceAccount:
    if account_type not in ACCOUNT_TYPES:
        raise ValueError(f"account_type must be one of: {', '.join(ACCOUNT_TYPES)}")
    account = FinanceAccount(
        id=str(uuid.uuid4()),
        owner=owner,
        name=name.strip(),
        institution=(institution or "").strip(),
        account_type=account_type,
        currency=currency or "USD",
        mask_last4=mask_last4,
        opening_balance_cents=opening_balance_cents,
        opening_balance_date=parse_optional_date(opening_balance_date),
        credit_limit_cents=credit_limit_cents,
    )
    db.add(account)
    db.commit()
    return account


def patch_account_for_owner(
    db: Session,
    owner: str,
    account_id: str,
    *,
    name: Optional[str] = None,
    institution: Optional[str] = None,
    account_type: Optional[str] = None,
    mask_last4: Optional[str] = None,
    opening_balance_cents: Optional[int] = None,
    opening_balance_date: Optional[str] = None,
    credit_limit_cents: Optional[int] = None,
    is_closed: Optional[bool] = None,
    display_order: Optional[int] = None,
) -> FinanceAccount:
    account = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    if not account:
        raise ValueError("Account not found")
    for field, val in (
        ("name", name),
        ("institution", institution),
        ("account_type", account_type),
        ("mask_last4", mask_last4),
        ("is_closed", is_closed),
        ("display_order", display_order),
    ):
        if val is not None:
            setattr(account, field, val)
    if opening_balance_cents is not None:
        account.opening_balance_cents = opening_balance_cents
    if opening_balance_date is not None:
        account.opening_balance_date = parse_optional_date(opening_balance_date)
    if credit_limit_cents is not None:
        account.credit_limit_cents = credit_limit_cents
    db.commit()
    return account


def delete_account_for_owner(db: Session, owner: str, account_id: str) -> None:
    account = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    if not account:
        raise ValueError("Account not found")
    tx_count = (
        db.query(FinanceTransaction)
        .filter(FinanceTransaction.account_id == account_id)
        .count()
    )
    if tx_count:
        raise ValueError(
            f"Account has {tx_count} transactions; delete batches first or close account"
        )
    db.delete(account)
    db.commit()
