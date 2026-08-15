"""Bank export parsers for manual CSV/OFX/QFX import."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional


FINANCE_IMPORT_MAX_ROWS = 50_000


@dataclass
class RowParseError:
    row: int
    message: str


@dataclass
class ParseResult:
    transactions: list["ParsedTransaction"]
    errors: list[RowParseError] = field(default_factory=list)


@dataclass
class ParsedTransaction:
    date: date
    amount_cents: int
    payee: str
    memo: str = ""
    check_number: str | None = None
    fitid: str | None = None
    bank_category: str | None = None
    dedup_hash: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def finalize(self, account_id: str = "") -> None:
        # Early-return is load-bearing: parsers set dedup_hash before account
        # assignment so the same NFCU file can be imported into two accounts.
        # Do not "fix" this by always rehashing with account_id.
        if self.dedup_hash:
            return
        key = "|".join([
            account_id,
            self.date.isoformat(),
            str(self.amount_cents),
            _normalize_payee(self.payee),
            self.fitid or "",
        ])
        self.dedup_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()


def _normalize_payee(payee: str) -> str:
    return re.sub(r"\s+", " ", (payee or "").strip().upper())


def _parse_decimal_amount(raw: str) -> int:
    cleaned = (raw or "").strip().replace("$", "").replace(",", "")
    if not cleaned:
        raise ValueError("empty amount")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1].strip()
    try:
        cents = int((Decimal(cleaned) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid amount: {raw!r}") from exc
    return cents


def _parse_date(raw: str, date_format: str | None = None) -> date:
    text = (raw or "").strip().strip('"')
    if not text:
        raise ValueError("empty date")
    formats = ["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y", "%Y/%m/%d", "%m/%d/%y"]
    if date_format:
        formats = [date_format, *formats]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognized date: {raw!r}")


def _read_csv_dicts(content: str) -> list[dict[str, str]]:
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    rows: list[dict[str, str]] = []
    for i, row in enumerate(reader):
        if i >= FINANCE_IMPORT_MAX_ROWS:
            raise ValueError(f"CSV exceeds {FINANCE_IMPORT_MAX_ROWS} row limit")
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
    return rows


def _header_map(row: dict[str, str]) -> dict[str, str]:
    return {(k or "").strip().lower(): k for k in row.keys()}


def _get_col(row: dict[str, str], *names: str) -> str:
    lower = _header_map(row)
    for name in names:
        key = lower.get(name.lower())
        if key and row.get(key, "").strip():
            return row[key].strip()
    return ""


def detect_csv_format(content: str) -> str:
    """Return preset id: csv_wells_fargo, csv_navy_federal, or csv_generic."""
    rows = _read_csv_dicts(content)
    if not rows:
        raise ValueError("CSV is empty")
    headers = {h.lower() for h in rows[0].keys()}
    if "amount" in headers and "description" in headers and "date" in headers:
        return "csv_wells_fargo"
    if "credit debit indicator" in headers and "posting date" in headers:
        return "csv_navy_federal"
    return "csv_generic"


def parse_wells_fargo_csv(content: str) -> ParseResult:
    rows = _read_csv_dicts(content)
    out: list[ParsedTransaction] = []
    errors: list[RowParseError] = []
    for i, row in enumerate(rows, start=1):
        date_raw = _get_col(row, "DATE", "Date")
        amount_raw = _get_col(row, "AMOUNT", "Amount")
        payee = _get_col(row, "DESCRIPTION", "Description", "Memo")
        check_no = _get_col(row, "CHECK #", "Check Number", "Check #") or None
        if not date_raw and not amount_raw:
            continue
        try:
            tx = ParsedTransaction(
                date=_parse_date(date_raw),
                amount_cents=_parse_decimal_amount(amount_raw),
                payee=payee,
                check_number=check_no,
                raw=dict(row),
            )
            tx.finalize()
            out.append(tx)
        except ValueError as exc:
            errors.append(RowParseError(row=i, message=str(exc)))
    return ParseResult(transactions=out, errors=errors)


def parse_navy_federal_csv(content: str) -> ParseResult:
    rows = _read_csv_dicts(content)
    out: list[ParsedTransaction] = []
    errors: list[RowParseError] = []
    for i, row in enumerate(rows, start=1):
        date_raw = _get_col(row, "Posting Date", "Transaction Date", "Date")
        amount_raw = _get_col(row, "Amount")
        indicator = _get_col(row, "Credit Debit Indicator").lower()
        payee = _get_col(row, "Description", "Memo")
        bank_cat = _get_col(row, "Category") or None
        if not date_raw and not amount_raw:
            continue
        try:
            cents = _parse_decimal_amount(amount_raw)
            if indicator == "debit":
                cents = -abs(cents)
            elif indicator == "credit":
                cents = abs(cents)
            elif cents > 0 and indicator:
                pass
            tx = ParsedTransaction(
                date=_parse_date(date_raw),
                amount_cents=cents,
                payee=payee,
                bank_category=bank_cat,
                raw=dict(row),
            )
            tx.finalize()
            out.append(tx)
        except ValueError as exc:
            errors.append(RowParseError(row=i, message=str(exc)))
    return ParseResult(transactions=out, errors=errors)


def _mapped_value(row: dict[str, str], mapping: dict[str, str], field: str, fallbacks: tuple[str, ...] = ()) -> str:
    key = mapping.get(field)
    if key and row.get(key):
        return row[key]
    header_lower = _header_map(row)
    for fb in fallbacks:
        col = header_lower.get(fb)
        if col and row.get(col):
            return row[col]
    return ""


def parse_generic_csv(
    content: str,
    mapping: dict[str, str] | None = None,
    options: dict | None = None,
) -> ParseResult:
    rows = _read_csv_dicts(content)
    if not rows:
        return ParseResult(transactions=[], errors=[])
    mapping = mapping or {}
    options = options or {}
    skip_rows = int(options.get("skip_rows") or 0)
    reverse_sign = bool(options.get("reverse_sign"))
    date_format = options.get("date_format") or None

    out: list[ParsedTransaction] = []
    errors: list[RowParseError] = []
    for i, row in enumerate(rows, start=1):
        if i <= skip_rows:
            continue
        date_raw = _mapped_value(row, mapping, "date", ("date", "posting date", "transaction date"))
        amount_raw = _mapped_value(row, mapping, "amount", ("amount",))
        debit_raw = _mapped_value(row, mapping, "debit", ("debit", "withdrawal"))
        credit_raw = _mapped_value(row, mapping, "credit", ("credit", "deposit"))
        payee = _mapped_value(row, mapping, "payee", ("description", "payee", "memo", "name"))
        memo = _mapped_value(row, mapping, "memo", ("memo", "notes"))
        check_number = _mapped_value(row, mapping, "check_number", ("check number", "check #")) or None
        fitid = _mapped_value(row, mapping, "fitid") or None
        bank_category = _mapped_value(row, mapping, "bank_category", ("category",)) or None

        if not date_raw and not amount_raw and not debit_raw and not credit_raw:
            continue

        try:
            if amount_raw:
                cents = _parse_decimal_amount(amount_raw)
            else:
                debit = abs(_parse_decimal_amount(debit_raw)) if debit_raw else 0
                credit = abs(_parse_decimal_amount(credit_raw)) if credit_raw else 0
                cents = credit - debit
            if reverse_sign:
                cents = -cents
            tx = ParsedTransaction(
                date=_parse_date(date_raw, date_format),
                amount_cents=cents,
                payee=payee,
                memo=memo,
                check_number=check_number,
                fitid=fitid,
                bank_category=bank_category,
                raw=dict(row),
            )
            tx.finalize()
            out.append(tx)
        except ValueError as exc:
            errors.append(RowParseError(row=i, message=str(exc)))
    return ParseResult(transactions=out, errors=errors)


def parse_csv(
    content: str,
    preset: str | None = None,
    mapping: dict[str, str] | None = None,
    options: dict | None = None,
) -> ParseResult:
    preset = preset or detect_csv_format(content)
    if preset == "csv_wells_fargo":
        return parse_wells_fargo_csv(content)
    if preset == "csv_navy_federal":
        return parse_navy_federal_csv(content)
    return parse_generic_csv(content, mapping, options)


def parse_ofx_qfx(content: bytes | str) -> list[ParsedTransaction]:
    """Parse OFX/QFX using ofxparse when installed."""
    try:
        from ofxparse import OfxParser
    except ImportError as exc:
        raise ValueError(
            "OFX/QFX import requires ofxparse. Install it or use CSV export from your bank."
        ) from exc

    if isinstance(content, str):
        content = content.encode("utf-8", errors="replace")
    if not content:
        raise ValueError("OFX/QFX file is empty")
    stream = io.BytesIO(content)
    try:
        ofx = OfxParser.parse(stream)
    except Exception as exc:
        raise ValueError(
            f"Could not parse OFX/QFX file ({type(exc).__name__}: {exc}). "
            "Check that the file is a valid OFX/QFX export from your bank, or use CSV."
        ) from exc
    out: list[ParsedTransaction] = []
    accounts: Iterable[Any] = []
    if getattr(ofx, "account", None):
        accounts = [ofx.account]
    elif getattr(ofx, "accounts", None):
        accounts = ofx.accounts or []

    for account in accounts:
        statement = getattr(account, "statement", None)
        if not statement:
            continue
        for tx in getattr(statement, "transactions", []) or []:
            dt = getattr(tx, "date", None) or getattr(tx, "user_date", None)
            if not dt:
                continue
            payee = (getattr(tx, "payee", None) or getattr(tx, "memo", None) or "").strip()
            memo = (getattr(tx, "memo", None) or "").strip()
            amount = getattr(tx, "amount", None)
            if amount is None:
                continue
            cents = int((Decimal(str(amount)) * 100).quantize(Decimal("1")))
            fitid = getattr(tx, "id", None) or getattr(tx, "fitid", None)
            parsed = ParsedTransaction(
                date=dt.date() if hasattr(dt, "date") else dt,
                amount_cents=cents,
                payee=payee,
                memo=memo,
                fitid=str(fitid) if fitid else None,
            )
            parsed.finalize()
            out.append(parsed)
    if not out and not list(accounts):
        raise ValueError("OFX/QFX file contains no accounts or transactions")
    return out


def detect_file_format(filename: str, content: bytes) -> str:
    name = (filename or "").lower()
    text_head = content[:512].decode("utf-8", errors="ignore").upper()
    if name.endswith((".qfx", ".ofx")) or "OFXHEADER" in text_head or "<OFX>" in text_head:
        return "ofx"
    return detect_csv_format(content.decode("utf-8", errors="replace"))


def parse_upload(
    filename: str,
    content: bytes,
    preset: str | None = None,
    mapping: dict[str, str] | None = None,
    options: dict | None = None,
) -> tuple[str, list[ParsedTransaction], list[RowParseError], dict[str, Any]]:
    if not content:
        raise ValueError("Upload file is empty")
    fmt = detect_file_format(filename, content)
    extra: dict[str, Any] = {"needs_mapping": False, "columns": [], "suggested_mapping": {}}
    if fmt == "ofx":
        return "ofx", parse_ofx_qfx(content), [], extra
    text = content.decode("utf-8", errors="replace")
    csv_preset = preset or fmt
    rows = _read_csv_dicts(text) if csv_preset != "ofx" else []
    headers = list(rows[0].keys()) if rows else []
    extra["columns"] = headers
    from integrations.finance.services.mappings import headers_are_obvious, suggest_mapping

    extra["suggested_mapping"] = suggest_mapping(headers)
    if csv_preset == "csv_generic" and not mapping and not headers_are_obvious(headers):
        extra["needs_mapping"] = True
        return csv_preset, [], [], extra
    result = parse_csv(text, csv_preset, mapping=mapping, options=options)
    return csv_preset, result.transactions, result.errors, extra
