"""Manual investing holdings. Snapshots, not bank CSV and not live quotes."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Optional

from sqlalchemy.orm import Session

from integrations.finance.models import FinanceAccount, utcnow_naive
from integrations.finance.models_investing import (
    ASSET_KINDS,
    FinanceInvestAsset,
    FinanceInvestValuation,
)
from integrations.finance.services.accounts import log_mutation, parse_optional_date

MILLISHARES_PER_SHARE = 1000


def ensure_invest_schema(engine) -> None:
    """Create invest tables if missing. Safe to call on every finance init."""
    FinanceInvestAsset.__table__.create(bind=engine, checkfirst=True)
    FinanceInvestValuation.__table__.create(bind=engine, checkfirst=True)


def millishares_from_input(
    *,
    shares_millishares: Optional[int] = None,
    shares: Optional[Any] = None,
    default: int = 0,
) -> int:
    if shares_millishares is not None:
        value = int(shares_millishares)
        if value < 0:
            raise ValueError("shares_millishares must be >= 0")
        return value
    if shares is None or shares == "":
        return default
    try:
        qty = Decimal(str(shares).strip().replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("shares must be a decimal number") from exc
    if qty < 0:
        raise ValueError("shares must be >= 0")
    milli = (qty * MILLISHARES_PER_SHARE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(milli)


def shares_string(millishares: int) -> str:
    qty = Decimal(int(millishares)) / Decimal(MILLISHARES_PER_SHARE)
    text = format(qty, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _as_of_date(raw: Optional[str]) -> date:
    if not raw:
        return utcnow_naive().date()
    parsed = parse_optional_date(raw)
    if parsed is None:
        raise ValueError("as_of must be YYYY-MM-DD")
    return parsed


def _nonneg_cents(value: Any, field: str) -> int:
    cents = int(value)
    if cents < 0:
        raise ValueError(f"{field} must be >= 0")
    return cents


def _validate_kind(asset_kind: str | None) -> str:
    kind = (asset_kind or "other").strip().lower()
    if kind not in ASSET_KINDS:
        raise ValueError(f"asset_kind must be one of: {', '.join(ASSET_KINDS)}")
    return kind


def _owned_account_id(db: Session, owner: str, account_id: Optional[str]) -> Optional[str]:
    if account_id is None:
        return None
    value = str(account_id).strip()
    if not value:
        return None
    row = (
        db.query(FinanceAccount)
        .filter(FinanceAccount.id == value, FinanceAccount.owner == owner)
        .first()
    )
    if not row:
        raise ValueError("account_id must be an account you own")
    return row.id


def unrealized_gain_cents(asset: FinanceInvestAsset) -> int:
    return int(asset.current_value_cents or 0) - int(asset.cost_basis_cents or 0)


def unrealized_gain_pct(asset: FinanceInvestAsset) -> Optional[float]:
    cost = int(asset.cost_basis_cents or 0)
    if cost <= 0:
        return None
    return round(unrealized_gain_cents(asset) / cost * 100.0, 4)


def asset_dict(asset: FinanceInvestAsset) -> dict[str, Any]:
    gain = unrealized_gain_cents(asset)
    pct = unrealized_gain_pct(asset)
    return {
        "id": asset.id,
        "name": asset.name,
        "symbol": asset.symbol or "",
        "asset_kind": asset.asset_kind,
        "account_id": asset.account_id,
        "shares_millishares": int(asset.shares_millishares or 0),
        "shares": shares_string(int(asset.shares_millishares or 0)),
        "cost_basis_cents": int(asset.cost_basis_cents or 0),
        "current_value_cents": int(asset.current_value_cents or 0),
        "unrealized_gain_cents": gain,
        "unrealized_gain_pct": pct,
        "notes": asset.notes or "",
        "archived": bool(asset.archived),
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
        "updated_at": asset.updated_at.isoformat() if asset.updated_at else None,
    }


def valuation_dict(row: FinanceInvestValuation) -> dict[str, Any]:
    return {
        "id": row.id,
        "asset_id": row.asset_id,
        "as_of": row.as_of.isoformat() if row.as_of else None,
        "value_cents": int(row.value_cents or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _get_owned(db: Session, owner: str, asset_id: str) -> Optional[FinanceInvestAsset]:
    return (
        db.query(FinanceInvestAsset)
        .filter(FinanceInvestAsset.id == asset_id, FinanceInvestAsset.owner == owner)
        .first()
    )


def _append_valuation(
    db: Session,
    asset: FinanceInvestAsset,
    *,
    value_cents: int,
    as_of: Optional[str] = None,
) -> FinanceInvestValuation:
    row = FinanceInvestValuation(
        id=str(uuid.uuid4()),
        owner=asset.owner,
        asset_id=asset.id,
        as_of=_as_of_date(as_of),
        value_cents=int(value_cents),
    )
    db.add(row)
    return row


def list_assets_for_owner(
    db: Session,
    owner: str,
    *,
    include_archived: bool = False,
    asset_kind: Optional[str] = None,
) -> list[FinanceInvestAsset]:
    q = db.query(FinanceInvestAsset).filter(FinanceInvestAsset.owner == owner)
    if not include_archived:
        q = q.filter(FinanceInvestAsset.archived == False)  # noqa: E712
    if asset_kind:
        q = q.filter(FinanceInvestAsset.asset_kind == _validate_kind(asset_kind))
    return q.order_by(FinanceInvestAsset.name.asc(), FinanceInvestAsset.id.asc()).all()


def get_asset_for_owner(db: Session, owner: str, asset_id: str) -> Optional[FinanceInvestAsset]:
    return _get_owned(db, owner, asset_id)


def create_asset_for_owner(
    db: Session,
    owner: str,
    *,
    name: str,
    symbol: str = "",
    asset_kind: str = "other",
    account_id: Optional[str] = None,
    shares_millishares: Optional[int] = None,
    shares: Optional[Any] = None,
    cost_basis_cents: int = 0,
    current_value_cents: int = 0,
    notes: str = "",
    actor: str = "user",
) -> FinanceInvestAsset:
    trimmed = (name or "").strip()
    if not trimmed:
        raise ValueError("name is required")
    millishares = millishares_from_input(shares_millishares=shares_millishares, shares=shares)
    cost = _nonneg_cents(cost_basis_cents, "cost_basis_cents")
    value = _nonneg_cents(current_value_cents, "current_value_cents")
    asset = FinanceInvestAsset(
        id=str(uuid.uuid4()),
        owner=owner,
        name=trimmed,
        symbol=(symbol or "").strip(),
        asset_kind=_validate_kind(asset_kind),
        account_id=_owned_account_id(db, owner, account_id),
        shares_millishares=millishares,
        cost_basis_cents=cost,
        current_value_cents=value,
        notes=(notes or "").strip(),
        archived=False,
    )
    db.add(asset)
    db.flush()
    if value != 0:
        _append_valuation(db, asset, value_cents=value)
    log_mutation(
        db,
        owner,
        action="create",
        entity_type="invest_asset",
        entity_id=asset.id,
        after=asset_dict(asset),
        actor=actor,
    )
    db.commit()
    db.refresh(asset)
    return asset


def patch_asset_for_owner(
    db: Session,
    owner: str,
    asset_id: str,
    *,
    name: Optional[str] = None,
    symbol: Optional[str] = None,
    asset_kind: Optional[str] = None,
    account_id: Optional[str] = None,
    clear_account: bool = False,
    shares_millishares: Optional[int] = None,
    shares: Optional[Any] = None,
    cost_basis_cents: Optional[int] = None,
    current_value_cents: Optional[int] = None,
    notes: Optional[str] = None,
    archived: Optional[bool] = None,
    actor: str = "user",
) -> Optional[FinanceInvestAsset]:
    asset = _get_owned(db, owner, asset_id)
    if not asset:
        return None
    before = asset_dict(asset)
    if name is not None:
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("name is required")
        asset.name = trimmed
    if symbol is not None:
        asset.symbol = symbol.strip()
    if asset_kind is not None:
        asset.asset_kind = _validate_kind(asset_kind)
    if clear_account:
        asset.account_id = None
    elif account_id is not None:
        asset.account_id = _owned_account_id(db, owner, account_id)
    if shares_millishares is not None or shares is not None:
        asset.shares_millishares = millishares_from_input(
            shares_millishares=shares_millishares,
            shares=shares,
            default=int(asset.shares_millishares or 0),
        )
    if cost_basis_cents is not None:
        asset.cost_basis_cents = _nonneg_cents(cost_basis_cents, "cost_basis_cents")
    value_changed = False
    if current_value_cents is not None:
        new_value = _nonneg_cents(current_value_cents, "current_value_cents")
        if new_value != int(asset.current_value_cents or 0):
            value_changed = True
        asset.current_value_cents = new_value
    if notes is not None:
        asset.notes = notes.strip()
    if archived is not None:
        asset.archived = bool(archived)
    if value_changed:
        _append_valuation(db, asset, value_cents=int(asset.current_value_cents or 0))
    log_mutation(
        db,
        owner,
        action="patch",
        entity_type="invest_asset",
        entity_id=asset.id,
        before=before,
        after=asset_dict(asset),
        actor=actor,
    )
    db.commit()
    db.refresh(asset)
    return asset


def delete_asset_for_owner(db: Session, owner: str, asset_id: str, *, actor: str = "user") -> bool:
    asset = _get_owned(db, owner, asset_id)
    if not asset:
        return False
    before = asset_dict(asset)
    db.query(FinanceInvestValuation).filter(FinanceInvestValuation.asset_id == asset.id).delete()
    db.delete(asset)
    log_mutation(
        db,
        owner,
        action="delete",
        entity_type="invest_asset",
        entity_id=asset_id,
        before=before,
        actor=actor,
    )
    db.commit()
    return True


def update_asset_value_for_owner(
    db: Session,
    owner: str,
    asset_id: str,
    *,
    current_value_cents: int,
    as_of: Optional[str] = None,
    shares_millishares: Optional[int] = None,
    shares: Optional[Any] = None,
    actor: str = "user",
) -> Optional[FinanceInvestAsset]:
    asset = _get_owned(db, owner, asset_id)
    if not asset:
        return None
    before = asset_dict(asset)
    asset.current_value_cents = _nonneg_cents(current_value_cents, "current_value_cents")
    if shares_millishares is not None or shares is not None:
        asset.shares_millishares = millishares_from_input(
            shares_millishares=shares_millishares,
            shares=shares,
            default=int(asset.shares_millishares or 0),
        )
    _append_valuation(db, asset, value_cents=asset.current_value_cents, as_of=as_of)
    log_mutation(
        db,
        owner,
        action="value",
        entity_type="invest_asset",
        entity_id=asset.id,
        before=before,
        after=asset_dict(asset),
        actor=actor,
    )
    db.commit()
    db.refresh(asset)
    return asset


def list_valuations_for_owner(
    db: Session,
    owner: str,
    asset_id: str,
) -> Optional[list[FinanceInvestValuation]]:
    asset = _get_owned(db, owner, asset_id)
    if not asset:
        return None
    return (
        db.query(FinanceInvestValuation)
        .filter(FinanceInvestValuation.asset_id == asset.id, FinanceInvestValuation.owner == owner)
        .order_by(FinanceInvestValuation.created_at.desc(), FinanceInvestValuation.id.desc())
        .all()
    )


def summary_for_owner(db: Session, owner: str) -> dict[str, Any]:
    assets = list_assets_for_owner(db, owner, include_archived=False)
    total_value = sum(int(a.current_value_cents or 0) for a in assets)
    total_cost = sum(int(a.cost_basis_cents or 0) for a in assets)
    gain = total_value - total_cost
    pct = round(gain / total_cost * 100.0, 4) if total_cost > 0 else None
    by_kind: dict[str, int] = {kind: 0 for kind in ASSET_KINDS}
    for asset in assets:
        by_kind[asset.asset_kind] = by_kind.get(asset.asset_kind, 0) + int(asset.current_value_cents or 0)
    allocation = []
    for kind in ASSET_KINDS:
        value = by_kind.get(kind, 0)
        if value == 0 and not any(a.asset_kind == kind for a in assets):
            continue
        allocation.append(
            {
                "asset_kind": kind,
                "value_cents": value,
                "pct": round(value / total_value * 100.0, 2) if total_value else 0.0,
            }
        )
    return {
        "total_current_value_cents": total_value,
        "total_cost_basis_cents": total_cost,
        "unrealized_gain_cents": gain,
        "unrealized_gain_pct": pct,
        "asset_count": len(assets),
        "allocation": allocation,
    }
