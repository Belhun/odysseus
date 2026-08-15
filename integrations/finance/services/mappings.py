"""Saved CSV column mappings and header fingerprints."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from integrations.finance.models import FinanceCsvMapping

OBVIOUS_DATE = ("date", "posting date", "transaction date", "trans date")
OBVIOUS_AMOUNT = ("amount", "amt")
OBVIOUS_PAYEE = ("description", "payee", "name", "memo")
OBVIOUS_DEBIT = ("debit", "withdrawal")
OBVIOUS_CREDIT = ("credit", "deposit")
OBVIOUS_MEMO = ("memo", "notes", "narrative")
OBVIOUS_FITID = ("fitid", "fit id", "transaction id", "ref", "reference")
OBVIOUS_CHECK = ("check number", "check #", "check")
OBVIOUS_BANK_CAT = ("category", "bank category")


def fingerprint_headers(headers: list[str]) -> str:
    return "|".join(sorted((h or "").strip().lower() for h in headers if (h or "").strip()))


def _match(headers: list[str], candidates: tuple[str, ...]) -> str | None:
    lower = {(h or "").strip().lower(): h for h in headers if (h or "").strip()}
    for cand in candidates:
        if cand in lower:
            return lower[cand]
    for key, original in lower.items():
        if any(cand in key for cand in candidates):
            return original
    return None


def suggest_mapping(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    date_col = _match(headers, OBVIOUS_DATE)
    if date_col:
        mapping["date"] = date_col
    amount_col = _match(headers, OBVIOUS_AMOUNT)
    if amount_col:
        mapping["amount"] = amount_col
    debit_col = _match(headers, OBVIOUS_DEBIT)
    if debit_col:
        mapping["debit"] = debit_col
    credit_col = _match(headers, OBVIOUS_CREDIT)
    if credit_col:
        mapping["credit"] = credit_col
    payee_col = _match(headers, OBVIOUS_PAYEE)
    if payee_col:
        mapping["payee"] = payee_col
    memo_col = _match(headers, OBVIOUS_MEMO)
    if memo_col and memo_col != payee_col:
        mapping["memo"] = memo_col
    fitid_col = _match(headers, OBVIOUS_FITID)
    if fitid_col:
        mapping["fitid"] = fitid_col
    check_col = _match(headers, OBVIOUS_CHECK)
    if check_col:
        mapping["check_number"] = check_col
    bank_col = _match(headers, OBVIOUS_BANK_CAT)
    if bank_col:
        mapping["bank_category"] = bank_col
    return mapping


def headers_are_obvious(headers: list[str], mapping: dict[str, str] | None = None) -> bool:
    suggested = mapping or suggest_mapping(headers)
    has_date = bool(suggested.get("date"))
    has_amount = bool(suggested.get("amount") or (suggested.get("debit") and suggested.get("credit")))
    has_payee = bool(suggested.get("payee"))
    return has_date and has_amount and has_payee


def list_mappings_for_owner(db: Session, owner: str) -> list[FinanceCsvMapping]:
    return (
        db.query(FinanceCsvMapping)
        .filter(FinanceCsvMapping.owner == owner)
        .order_by(FinanceCsvMapping.name)
        .all()
    )


def mapping_dict(row: FinanceCsvMapping) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "fingerprint": row.fingerprint,
        "mapping": row.mapping or {},
        "options": row.options or {},
    }


def save_mapping_for_owner(
    db: Session,
    owner: str,
    *,
    name: str,
    fingerprint: str,
    mapping: dict[str, str],
    options: Optional[dict] = None,
) -> FinanceCsvMapping:
    existing = (
        db.query(FinanceCsvMapping)
        .filter(FinanceCsvMapping.owner == owner, FinanceCsvMapping.fingerprint == fingerprint)
        .first()
    )
    if existing:
        existing.name = (name or existing.name)[:120]
        existing.mapping = mapping
        existing.options = options or existing.options
        db.commit()
        return existing
    row = FinanceCsvMapping(
        id=str(uuid.uuid4()),
        owner=owner,
        name=(name or "Saved mapping")[:120],
        fingerprint=fingerprint,
        mapping=mapping,
        options=options or {},
    )
    db.add(row)
    db.commit()
    return row


def get_mapping_by_id(db: Session, owner: str, mapping_id: str) -> FinanceCsvMapping | None:
    return (
        db.query(FinanceCsvMapping)
        .filter(FinanceCsvMapping.id == mapping_id, FinanceCsvMapping.owner == owner)
        .first()
    )


def get_mapping_by_fingerprint(db: Session, owner: str, fingerprint: str) -> FinanceCsvMapping | None:
    return (
        db.query(FinanceCsvMapping)
        .filter(FinanceCsvMapping.owner == owner, FinanceCsvMapping.fingerprint == fingerprint)
        .first()
    )


def parse_json_object(raw: str | None) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("mapping/options must be JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("mapping/options must be a JSON object")
    return data
