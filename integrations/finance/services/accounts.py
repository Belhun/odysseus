"""Account CRUD for the Finance plugin."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from integrations.finance.models import (
    ACCOUNT_PURPOSES,
    ACCOUNT_RAILS,
    FinanceAccount,
    FinanceMutationLog,
    FinanceTransaction,
)
from integrations.finance.services.balances import account_balance_snapshot, iso_date

ACCOUNT_TYPES = ("checking", "savings", "credit_card", "loan", "cash", "other")


def parse_optional_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    return datetime.strptime(raw[:10], "%Y-%m-%d").date()


def log_mutation(
    db: Session,
    owner: str,
    *,
    action: str,
    entity_type: str,
    entity_id: str,
    before: dict | None = None,
    after: dict | None = None,
    actor: str = "user",
) -> None:
    db.add(
        FinanceMutationLog(
            id=str(uuid.uuid4()),
            owner=owner,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=json.dumps(before) if before is not None else None,
            after_json=json.dumps(after) if after is not None else None,
        )
    )


def _validate_purpose(purpose: str | None) -> str:
    value = (purpose or "operating").strip().lower()
    if value not in ACCOUNT_PURPOSES:
        raise ValueError(f"purpose must be one of: {', '.join(ACCOUNT_PURPOSES)}")
    return value


def _validate_rail(purpose: str, rail: str | None) -> str | None:
    if rail is None or rail == "":
        return None
    value = str(rail).strip().lower()
    if value not in ACCOUNT_RAILS:
        raise ValueError(f"rail must be one of: {', '.join(ACCOUNT_RAILS)}")
    if purpose != "processor":
        raise ValueError("rail is only valid when purpose is processor")
    return value


def account_dict(db: Session, account: FinanceAccount) -> dict[str, Any]:
    snap = account_balance_snapshot(db, account)
    return {
        "id": account.id,
        "name": account.name,
        "institution": account.institution or "",
        "account_type": account.account_type,
        "purpose": account.purpose or "operating",
        "rail": account.rail,
        "currency": account.currency,
        "mask_last4": account.mask_last4,
        "opening_balance_cents": account.opening_balance_cents or 0,
        "opening_balance_date": iso_date(account.opening_balance_date),
        "credit_limit_cents": account.credit_limit_cents,
        "is_closed": bool(account.is_closed),
        "display_order": account.display_order or 0,
        "posted_cents": snap["posted_cents"],
        "balance_cents": snap["balance_cents"],
        "posted_pin_cents": snap["posted_pin_cents"],
        "posted_pin_as_of": snap["posted_pin_as_of"],
        "posted_pin_delta_cents": snap["posted_pin_delta_cents"],
        "available_cents": snap["available_cents"],
        "available_as_of": snap["available_as_of"],
        "available_age_days": snap["available_age_days"],
        "posted_pin_age_days": snap["posted_pin_age_days"],
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


def _get_owned_account(db: Session, owner: str, account_id: str) -> FinanceAccount:
    account = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == account_id, FinanceAccount.owner == owner)
        .first()
    )
    if not account:
        raise ValueError("Account not found")
    return account


def create_account_for_owner(
    db: Session,
    owner: str,
    *,
    name: str,
    institution: str = "",
    account_type: str = "checking",
    purpose: str = "operating",
    rail: Optional[str] = None,
    currency: str = "USD",
    mask_last4: Optional[str] = None,
    opening_balance_cents: int = 0,
    opening_balance_date: Optional[str] = None,
    credit_limit_cents: Optional[int] = None,
    posted_pin_cents: Optional[int] = None,
    posted_pin_as_of: Optional[str] = None,
    available_cents: Optional[int] = None,
    available_as_of: Optional[str] = None,
    actor: str = "user",
) -> FinanceAccount:
    if account_type not in ACCOUNT_TYPES:
        raise ValueError(f"account_type must be one of: {', '.join(ACCOUNT_TYPES)}")
    purpose_val = _validate_purpose(purpose)
    rail_val = _validate_rail(purpose_val, rail)
    account = FinanceAccount(
        id=str(uuid.uuid4()),
        owner=owner,
        name=name.strip(),
        institution=(institution or "").strip(),
        account_type=account_type,
        purpose=purpose_val,
        rail=rail_val,
        currency=currency or "USD",
        mask_last4=mask_last4,
        opening_balance_cents=opening_balance_cents,
        opening_balance_date=parse_optional_date(opening_balance_date),
        credit_limit_cents=credit_limit_cents,
        posted_pin_cents=posted_pin_cents,
        posted_pin_as_of=parse_optional_date(posted_pin_as_of),
        available_cents=available_cents,
        available_as_of=parse_optional_date(available_as_of),
    )
    db.add(account)
    if any(v is not None for v in (posted_pin_cents, posted_pin_as_of, available_cents, available_as_of)):
        log_mutation(
            db,
            owner,
            action="pin",
            entity_type="account",
            entity_id=account.id,
            after={
                "posted_pin_cents": posted_pin_cents,
                "posted_pin_as_of": posted_pin_as_of,
                "available_cents": available_cents,
                "available_as_of": available_as_of,
            },
            actor=actor,
        )
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
    purpose: Optional[str] = None,
    rail: Optional[str] = None,
    mask_last4: Optional[str] = None,
    opening_balance_cents: Optional[int] = None,
    opening_balance_date: Optional[str] = None,
    credit_limit_cents: Optional[int] = None,
    is_closed: Optional[bool] = None,
    display_order: Optional[int] = None,
    posted_pin_cents: Optional[int] = None,
    posted_pin_as_of: Optional[str] = None,
    available_cents: Optional[int] = None,
    available_as_of: Optional[str] = None,
    clear_posted_pin: bool = False,
    clear_available: bool = False,
    actor: str = "user",
) -> FinanceAccount:
    account = _get_owned_account(db, owner, account_id)
    if account_type is not None and account_type not in ACCOUNT_TYPES:
        raise ValueError(f"account_type must be one of: {', '.join(ACCOUNT_TYPES)}")
    pin_touched = any(
        v is not None
        for v in (posted_pin_cents, posted_pin_as_of, available_cents, available_as_of)
    ) or clear_posted_pin or clear_available
    before_pins = None
    if pin_touched:
        before_pins = {
            "posted_pin_cents": account.posted_pin_cents,
            "posted_pin_as_of": iso_date(account.posted_pin_as_of),
            "available_cents": account.available_cents,
            "available_as_of": iso_date(account.available_as_of),
        }
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
    if purpose is not None:
        account.purpose = _validate_purpose(purpose)
    next_purpose = account.purpose or "operating"
    if rail is not None:
        account.rail = _validate_rail(next_purpose, rail)
    elif purpose is not None and next_purpose != "processor":
        account.rail = None
    if opening_balance_cents is not None:
        account.opening_balance_cents = opening_balance_cents
    if opening_balance_date is not None:
        account.opening_balance_date = parse_optional_date(opening_balance_date)
    if credit_limit_cents is not None:
        account.credit_limit_cents = credit_limit_cents
    if clear_posted_pin:
        account.posted_pin_cents = None
        account.posted_pin_as_of = None
    else:
        if posted_pin_cents is not None:
            account.posted_pin_cents = posted_pin_cents
        if posted_pin_as_of is not None:
            account.posted_pin_as_of = parse_optional_date(posted_pin_as_of)
    if clear_available:
        account.available_cents = None
        account.available_as_of = None
    else:
        if available_cents is not None:
            account.available_cents = available_cents
        if available_as_of is not None:
            account.available_as_of = parse_optional_date(available_as_of)
    if pin_touched:
        log_mutation(
            db,
            owner,
            action="pin",
            entity_type="account",
            entity_id=account.id,
            before=before_pins,
            after={
                "posted_pin_cents": account.posted_pin_cents,
                "posted_pin_as_of": iso_date(account.posted_pin_as_of),
                "available_cents": account.available_cents,
                "available_as_of": iso_date(account.available_as_of),
            },
            actor=actor,
        )
    db.commit()
    return account


def pin_account_balances(
    db: Session,
    owner: str,
    account_id: str,
    *,
    posted_pin_cents: Optional[int] = None,
    posted_pin_as_of: Optional[str] = None,
    available_cents: Optional[int] = None,
    available_as_of: Optional[str] = None,
    clear_posted_pin: bool = False,
    clear_available: bool = False,
    actor: str = "user",
) -> FinanceAccount:
    if all(
        v is None
        for v in (posted_pin_cents, posted_pin_as_of, available_cents, available_as_of)
    ) and not clear_posted_pin and not clear_available:
        raise ValueError("At least one pin field is required")
    return patch_account_for_owner(
        db,
        owner,
        account_id,
        posted_pin_cents=posted_pin_cents,
        posted_pin_as_of=posted_pin_as_of,
        available_cents=available_cents,
        available_as_of=available_as_of,
        clear_posted_pin=clear_posted_pin,
        clear_available=clear_available,
        actor=actor,
    )


def delete_account_for_owner(db: Session, owner: str, account_id: str) -> None:
    account = _get_owned_account(db, owner, account_id)
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
