"""Convert Wells Fargo checking/savings statement PDFs into signed CSV rows.

Handles 2019-era packed text objects and 2024-era column-separated layouts.
Writes an Odysseus import CSV with opening-posted metadata.
"""

from __future__ import annotations

import csv
import io
import re
import tempfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from itertools import product
from pathlib import Path
from typing import Iterable, Sequence


class WellsStatementError(ValueError):
    """PDF is not a parseable single-account Wells statement."""


MONTH_NAME = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_ALT = "|".join(MONTH_NAME)

HEADER_DATE_RE = re.compile(
    rf"^({MONTH_ALT})\s+(\d{{1,2}}),\s+(\d{{4}})$",
    re.I,
)
PERIOD_RANGE_RE = re.compile(
    rf"({MONTH_ALT})\s+(\d{{1,2}}),\s+(\d{{4}})\s*-\s*({MONTH_ALT})\s+(\d{{1,2}}),\s+(\d{{4}})",
    re.I,
)
MD_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")
ROW_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})(?:\s+|$)")
MONEY_RE = re.compile(r"^\$?\s*-?\s*[\d,]+\.\d{2}$")
MONEY_TOKEN_RE = re.compile(r"-?\$?[\d,]+\.\d{2}")
FEE_PERIOD_RE = re.compile(
    r"Fee period\s+(\d{1,2})/(\d{1,2})/(\d{4})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{4})",
    re.I,
)
BEGIN_AMT_RE = re.compile(
    r"Beginning balance on\s+(\d{1,2}/\d{1,2})\s+(-?\$?\s*[\d,]+\.\d{2})",
    re.I,
)
END_AMT_RE = re.compile(
    r"Ending balance on\s+(\d{1,2}/\d{1,2})\s+(-?\$?\s*[\d,]+\.\d{2})",
    re.I,
)
DEPOSITS_AMT_RE = re.compile(r"Deposits/Additions\s+(-?\$?\s*[\d,]+\.\d{2})", re.I)
WITHDRAW_AMT_RE = re.compile(r"Withdrawals/Subtractions\s+(-?\$?\s*[\d,]+\.\d{2})", re.I)
ACCOUNT_RE = re.compile(r"Account number:\s*(\d+)", re.I)

DEFAULT_DEPOSIT_X = 539.0
DEFAULT_WITHDRAW_X = 611.0
DEFAULT_BALANCE_X = 700.0
PORTRAIT_DEPOSIT_X = 418.0
PORTRAIT_WITHDRAW_X = 487.0
PORTRAIT_BALANCE_X = 530.0
LINE_Y_TOLERANCE = 3.5
DATE_X_MAX = 130.0
CHECK_X_MAX = 195.0
SKIP_XY_ORIGIN = True
LANDSCAPE_MIN_X = 650.0

INFLOW_HINTS = (
    "atm cash deposit",
    "edposit",
    "direct deposit",
    "payroll",
    "online transfer from",
    "purchase return",
    "mobile deposit",
    "zelle from",
)
OUTFLOW_HINTS = (
    "purchase authorized",
    "recurring payment",
    "overdraft fee",
    "monthly service fee",
    "online transfer to",
    "recurring transfer to",
    "withdrawal",
    "zelle to",
)


@dataclass(frozen=True)
class TextItem:
    x: float
    y: float
    text: str


@dataclass
class ColumnXs:
    deposit: float = DEFAULT_DEPOSIT_X
    withdraw: float = DEFAULT_WITHDRAW_X
    balance: float = DEFAULT_BALANCE_X


@dataclass
class StatementTxn:
    date: date
    amount_cents: int
    payee: str
    check_number: str | None = None
    daily_balance_cents: int | None = None
    source_pdf: str = ""
    statement_start: date | None = None
    statement_end: date | None = None


@dataclass
class ParsedStatement:
    source_pdf: str
    product: str
    period_start: date
    period_end: date
    beginning_cents: int
    ending_cents: int
    deposits_cents: int
    withdrawals_cents: int
    transactions: list[StatementTxn]
    account_last4: str | None = None


@dataclass
class ConvertResult:
    transactions: list[StatementTxn]
    opening_posted_cents: int
    opening_as_of: date
    last_ending_cents: int
    last_ending_date: date
    statements: list[ParsedStatement]
    warnings: list[str] = field(default_factory=list)
    bank_csv_names: list[str] = field(default_factory=list)
    bank_matched_count: int = 0
    bank_appended_count: int = 0
    bank_skipped_pending_count: int = 0
    bank_skipped_overlap_count: int = 0


def parse_money_cents(raw: str) -> int:
    cleaned = (raw or "").strip().replace("$", "").replace(",", "").replace(" ", "")
    if not cleaned:
        raise WellsStatementError("empty amount")
    try:
        return int((Decimal(cleaned) * 100).quantize(Decimal("1")))
    except (InvalidOperation, ValueError) as exc:
        raise WellsStatementError(f"invalid amount: {raw!r}") from exc


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) / 100:.2f}"


def format_dollars(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def classify_amount_column(x: float, cols: ColumnXs) -> str:
    deposit_withdraw_mid = (cols.deposit + cols.withdraw) / 2
    withdraw_balance_mid = (cols.withdraw + cols.balance) / 2
    if x >= withdraw_balance_mid:
        return "balance"
    if x >= deposit_withdraw_mid:
        return "withdraw"
    if x >= cols.deposit - 50:
        return "deposit"
    return "other"


def _peel_trailing_amounts(text: str) -> tuple[str, list[int]]:
    rest = (text or "").rstrip()
    found: list[int] = []
    while len(found) < 2:
        match = re.search(r"(-?\$?[\d,]+\.\d{2})$", rest)
        if not match:
            break
        start = match.start()
        if start > 0 and not rest[start - 1].isspace():
            break
        found.insert(0, parse_money_cents(match.group(1)))
        rest = rest[:start].rstrip()
    return rest, found


def _is_pure_amount_text(text: str) -> bool:
    leftover = MONEY_TOKEN_RE.sub("", text or "")
    leftover = re.sub(r"[\s,]+", "", leftover)
    return bool(MONEY_TOKEN_RE.search(text or "")) and leftover == ""


def _extract_items(page) -> list[TextItem]:
    items: list[TextItem] = []

    def visitor(text, cm, tm, font_dict, font_size):
        raw = (text or "").replace("\n", "").strip()
        if not raw:
            return
        x = float(tm[4])
        y = float(tm[5])
        if SKIP_XY_ORIGIN and x == 0.0 and y == 0.0:
            return
        items.append(TextItem(x=x, y=y, text=raw))

    page.extract_text(visitor_text=visitor)
    return items


def extract_pdf_items(path: Path) -> list[list[TextItem]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise WellsStatementError(f"{path.name}: cannot read PDF ({exc})") from exc
    if not reader.pages:
        raise WellsStatementError(f"{path.name}: PDF has no pages")
    return [_extract_items(page) for page in reader.pages]


def _cluster_lines(items: Sequence[TextItem]) -> list[list[TextItem]]:
    ordered = sorted(items, key=lambda it: (-it.y, it.x))
    lines: list[list[TextItem]] = []
    current: list[TextItem] = []
    current_y: float | None = None
    for item in ordered:
        if current_y is None or abs(item.y - current_y) <= LINE_Y_TOLERANCE:
            current.append(item)
            if current_y is None:
                current_y = item.y
        else:
            lines.append(current)
            current = [item]
            current_y = item.y
    if current:
        lines.append(current)
    return lines


def _line_text(line: Sequence[TextItem]) -> str:
    return " ".join(item.text for item in line)


def _parse_named_date(month: str, day: str, year: str) -> date:
    return date(int(year), MONTH_NAME[month.lower()], int(day))


def _find_header_date(pages: Sequence[Sequence[TextItem]]) -> date | None:
    for page in pages:
        for item in page:
            match = HEADER_DATE_RE.match(item.text)
            if match:
                return _parse_named_date(match.group(1), match.group(2), match.group(3))
    return None


def _date_from_md(md: str, period_end: date) -> date:
    match = MD_RE.match(md.strip())
    if not match:
        raise WellsStatementError(f"not a month/day date: {md!r}")
    month, day = int(match.group(1)), int(match.group(2))
    try:
        candidate = date(period_end.year, month, day)
    except ValueError:
        candidate = date(period_end.year - 1, month, day)
    if candidate > period_end:
        candidate = date(period_end.year - 1, month, day)
    return candidate


def _assign_txn_date(month: int, day: int, period_start: date, period_end: date) -> date:
    window_start = period_start - timedelta(days=7)
    window_end = period_end + timedelta(days=7)
    candidates: list[date] = []
    for year in (period_end.year, period_start.year, period_end.year - 1, period_end.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    in_period = [d for d in candidates if period_start <= d <= period_end]
    if in_period:
        return in_period[0]
    in_window = [d for d in candidates if window_start <= d <= window_end]
    if in_window:
        return min(in_window, key=lambda d: min(abs((d - period_start).days), abs((d - period_end).days)))
    raise WellsStatementError(
        f"date {month}/{day} is outside statement period "
        f"{period_start.isoformat()}-{period_end.isoformat()}"
    )


def _is_landscape(pages: Sequence[Sequence[TextItem]]) -> bool:
    max_x = max((item.x for page in pages for item in page), default=0.0)
    return max_x >= LANDSCAPE_MIN_X


def _detect_columns(pages: Sequence[Sequence[TextItem]]) -> ColumnXs:
    cols = ColumnXs()
    found_deposit = found_withdraw = found_balance = False
    packed_header = False
    for page in pages:
        for item in page:
            if item.text == "Deposits/":
                cols.deposit = item.x
                found_deposit = True
            elif item.text == "Withdrawals/":
                cols.withdraw = item.x
                found_withdraw = True
            elif item.text == "Ending daily":
                cols.balance = item.x
                found_balance = True
            elif "Deposits/" in item.text and "Withdrawals/" in item.text:
                packed_header = True
        if found_deposit and found_withdraw and found_balance:
            return cols
    if packed_header or not _is_landscape(pages):
        return ColumnXs(
            deposit=PORTRAIT_DEPOSIT_X,
            withdraw=PORTRAIT_WITHDRAW_X,
            balance=PORTRAIT_BALANCE_X,
        )
    return cols


def _parse_summary(pages: Sequence[Sequence[TextItem]], header_date: date | None) -> dict:
    all_items = [item for page in pages for item in page]
    blob = "\n".join(item.text for item in all_items)
    lower = blob.lower()
    period_summaries = lower.count("statement period activity summary")
    bare_summaries = 0
    if period_summaries == 0:
        bare_summaries = lower.count("activity summary")
    total = period_summaries or bare_summaries
    if total == 0:
        raise WellsStatementError("no statement activity summary (not a Wells statement?)")
    if total > 1:
        raise WellsStatementError(
            "combined multi-account statement; split to one account per PDF"
        )

    begin = BEGIN_AMT_RE.search(blob)
    end = END_AMT_RE.search(blob)
    deposits = DEPOSITS_AMT_RE.search(blob)
    withdrawals = WITHDRAW_AMT_RE.search(blob)
    if not begin or not end or not deposits or not withdrawals:
        raise WellsStatementError("could not read summary beginning/ending/deposits/withdrawals")

    fee = FEE_PERIOD_RE.search(blob)
    period_range = PERIOD_RANGE_RE.search(blob)
    if fee:
        period_start = date(int(fee.group(3)), int(fee.group(1)), int(fee.group(2)))
        period_end = date(int(fee.group(6)), int(fee.group(4)), int(fee.group(5)))
    elif period_range:
        period_start = _parse_named_date(
            period_range.group(1), period_range.group(2), period_range.group(3)
        )
        period_end = _parse_named_date(
            period_range.group(4), period_range.group(5), period_range.group(6)
        )
    elif header_date:
        period_end = header_date
        period_start = _date_from_md(begin.group(1), period_end)
    else:
        raise WellsStatementError("no statement date in header")

    last4 = None
    acct = ACCOUNT_RE.search(blob)
    if acct:
        last4 = acct.group(1)[-4:]

    product = ""
    for item in all_items:
        text = item.text.lower()
        if text.startswith("wells fargo") and ("checking" in text or "savings" in text):
            product = item.text
            break

    amounts = {
        "beginning": parse_money_cents(begin.group(2)),
        "ending": parse_money_cents(end.group(2)),
        "deposits": abs(parse_money_cents(deposits.group(1))),
        "withdrawals": abs(parse_money_cents(withdrawals.group(1))),
    }
    expected = amounts["beginning"] + amounts["deposits"] - amounts["withdrawals"]
    if expected != amounts["ending"]:
        raise WellsStatementError(
            "summary does not foot: beginning "
            f"{format_dollars(amounts['beginning'])} + deposits "
            f"{format_dollars(amounts['deposits'])} - withdrawals "
            f"{format_dollars(amounts['withdrawals'])} = {format_dollars(expected)}, "
            f"statement ending is {format_dollars(amounts['ending'])}"
        )

    return {
        "period_start": period_start,
        "period_end": period_end,
        "account_last4": last4,
        "product": product,
        **amounts,
    }


def _is_history_header(joined: str) -> bool:
    lower = joined.lower()
    if "description" in lower and "additions" in lower:
        return True
    if "deposits/" in lower and "withdrawals/" in lower:
        return True
    if lower.strip() in {"date", "description", "additions", "subtractions", "balance", "number", "check"}:
        return True
    return False


def _is_history_stop(joined: str) -> bool:
    lower = joined.lower()
    if lower.startswith("ending balance on"):
        return True
    if lower.startswith("totals"):
        return True
    if lower.startswith("the ending daily balance does not reflect"):
        return True
    if lower.startswith("summary of overdraft"):
        return True
    if lower.startswith("worksheet to balance"):
        return True
    if lower.startswith("monthly service fee summary"):
        return True
    return False


def _sign_from_payee(payee: str) -> int | None:
    lower = (payee or "").lower()
    if any(hint in lower for hint in INFLOW_HINTS):
        return 1
    if any(hint in lower for hint in OUTFLOW_HINTS):
        return -1
    return None


def _apply_line_amounts(current: dict, line: Sequence[TextItem], cols: ColumnXs, source_name: str) -> None:
    for item in line:
        if not _is_pure_amount_text(item.text):
            continue
        _rest, values = _peel_trailing_amounts(item.text)
        if not values:
            values = [parse_money_cents(tok) for tok in MONEY_TOKEN_RE.findall(item.text)]
        kind = classify_amount_column(item.x, cols)
        if len(values) >= 2:
            amount, daily = values[0], values[1]
            if current["amount_cents"] is None:
                if kind == "deposit":
                    current["amount_cents"] = abs(amount)
                else:
                    current["amount_cents"] = -abs(amount)
            current["daily_balance_cents"] = daily
            continue
        cents = values[0]
        if kind == "deposit":
            if current["amount_cents"] is not None:
                raise WellsStatementError(f"{source_name}: {current['date']} has two amounts")
            current["amount_cents"] = abs(cents)
        elif kind == "withdraw":
            if current["amount_cents"] is not None:
                raise WellsStatementError(f"{source_name}: {current['date']} has two amounts")
            current["amount_cents"] = -abs(cents)
        elif kind == "balance":
            current["daily_balance_cents"] = cents
        elif current["amount_cents"] is None:
            current["amount_cents"] = abs(cents)
            current["sign_unknown"] = True


def _line_payee_parts(line: Sequence[TextItem], date_item: TextItem | None) -> tuple[str, list[int]]:
    parts: list[str] = []
    trailing: list[int] = []
    for item in line:
        if date_item is not None and item is date_item and MD_RE.match(item.text):
            continue
        if _is_pure_amount_text(item.text):
            continue
        if DATE_X_MAX < item.x < CHECK_X_MAX and item.text.isdigit() and len(item.text) <= 10:
            continue
        text = item.text
        text = re.sub(r"^\d{1,2}/\d{1,2}\s+", "", text)
        text, peeled = _peel_trailing_amounts(text)
        if peeled:
            trailing = peeled
        if text.strip():
            parts.append(text.strip())
    return " ".join(parts).strip(), trailing


def _parse_history(
    pages: Sequence[Sequence[TextItem]],
    cols: ColumnXs,
    period_start: date,
    period_end: date,
    source_name: str,
) -> list[StatementTxn]:
    txns: list[StatementTxn] = []
    current: dict | None = None
    in_history = False
    stopped = False

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        if current.get("amount_cents") is None:
            raise WellsStatementError(
                f"{source_name}: transaction {current.get('date')} {current.get('payee')!r} "
                "has no amount"
            )
        payee = re.sub(r"\s+", " ", (current.get("payee") or "").strip())
        if not payee:
            raise WellsStatementError(f"{source_name}: transaction {current['date']} has no description")
        amount = int(current["amount_cents"])
        if current.get("sign_unknown"):
            hint = _sign_from_payee(payee)
            if hint is not None:
                amount = abs(amount) * hint
        txns.append(
            StatementTxn(
                date=current["date"],
                amount_cents=amount,
                payee=payee,
                check_number=current.get("check_number"),
                daily_balance_cents=current.get("daily_balance_cents"),
                source_pdf=source_name,
                statement_start=period_start,
                statement_end=period_end,
            )
        )
        current = None

    for page in pages:
        if stopped:
            break
        for line in _cluster_lines(page):
            joined = _line_text(line)
            if "transaction history" in joined.lower():
                in_history = True
                continue
            if not in_history:
                continue
            if _is_history_stop(joined):
                flush()
                stopped = True
                break
            if _is_history_header(joined):
                continue

            date_item = next(
                (item for item in line if item.x <= DATE_X_MAX and MD_RE.match(item.text)),
                None,
            )
            row_match = ROW_DATE_RE.match(joined.strip())
            left_x = min((item.x for item in line), default=999)
            starts_new_row = False
            if date_item:
                starts_new_row = True
            elif row_match and left_x <= DATE_X_MAX:
                starts_new_row = True
            if starts_new_row:
                flush()
                if date_item:
                    month, day = (int(p) for p in date_item.text.split("/"))
                else:
                    month, day = int(row_match.group(1)), int(row_match.group(2))
                current = {
                    "date": _assign_txn_date(month, day, period_start, period_end),
                    "payee": "",
                    "amount_cents": None,
                    "check_number": None,
                    "daily_balance_cents": None,
                    "sign_unknown": False,
                }

            if current is None:
                continue

            for item in line:
                if (
                    DATE_X_MAX < item.x < CHECK_X_MAX
                    and item.text.isdigit()
                    and len(item.text) <= 10
                ):
                    current["check_number"] = item.text

            payee_part, trailing = _line_payee_parts(line, date_item)
            lead = re.match(r"^(\$?-?[\d,]+\.\d{2}|-?\$[\d,]+\.\d{2})\s+(.*)$", payee_part)
            if lead and current["amount_cents"] is None:
                current["amount_cents"] = parse_money_cents(lead.group(1))
                current["sign_unknown"] = True
                payee_part = lead.group(2).strip()
            if payee_part:
                current["payee"] = f"{current['payee']} {payee_part}".strip()
            _apply_line_amounts(current, line, cols, source_name)
            if current["amount_cents"] is None and trailing:
                current["amount_cents"] = trailing[0]
                current["sign_unknown"] = True
                if len(trailing) > 1:
                    current["daily_balance_cents"] = trailing[1]
            elif current["daily_balance_cents"] is None and len(trailing) > 1:
                current["daily_balance_cents"] = trailing[1]

    flush()
    if not txns:
        raise WellsStatementError(f"{source_name}: no transaction history rows")
    return txns


def _is_sign_ambiguous(payee: str) -> bool:
    lower = (payee or "").lower()
    if "paypal inst xfer" in lower or ("inst xfer" in lower and "paypal" in lower):
        return True
    if "acorns" in lower:
        return True
    return False


def _fit_group_to_target(
    group: list[StatementTxn],
    start_cents: int,
    target_cents: int,
    source_pdf: str,
) -> None:
    def total() -> int:
        return start_cents + sum(txn.amount_cents for txn in group)

    if total() == target_cents:
        return
    diff = total() - target_cents
    candidates = [txn for txn in group if 2 * abs(txn.amount_cents) == abs(diff)]
    preferred = [txn for txn in candidates if _is_sign_ambiguous(txn.payee)] or candidates
    if len(preferred) == 1:
        txn = preferred[0]
        txn.amount_cents = -txn.amount_cents
        if total() == target_cents:
            return
        txn.amount_cents = -txn.amount_cents
    ambiguous = [txn for txn in group if _is_sign_ambiguous(txn.payee)]
    if 1 <= len(ambiguous) <= 8:
        originals = [txn.amount_cents for txn in ambiguous]
        for signs in product((-1, 1), repeat=len(ambiguous)):
            for txn, sign, original in zip(ambiguous, signs, originals):
                txn.amount_cents = abs(original) * sign
            if total() == target_cents:
                return
        for txn, original in zip(ambiguous, originals):
            txn.amount_cents = original
    raise WellsStatementError(
        f"{source_pdf}: running balance cannot reach printed daily "
        f"{format_dollars(target_cents)} on {group[-1].date.isoformat()} "
        f"({group[-1].payee})"
    )


def _resolve_running_signs(stmt: ParsedStatement) -> None:
    running = stmt.beginning_cents
    i = 0
    n = len(stmt.transactions)
    while i < n:
        j = i
        while j < n and stmt.transactions[j].daily_balance_cents is None:
            j += 1
        if j < n:
            target = stmt.transactions[j].daily_balance_cents
            group = stmt.transactions[i : j + 1]
            next_i = j + 1
        else:
            target = stmt.ending_cents
            group = stmt.transactions[i:]
            next_i = n
        if not group:
            break
        _fit_group_to_target(group, running, target, stmt.source_pdf)
        running = target
        i = next_i


def _assert_running_balance(stmt: ParsedStatement) -> None:
    running = stmt.beginning_cents
    for txn in stmt.transactions:
        running += txn.amount_cents
        if txn.daily_balance_cents is not None and txn.daily_balance_cents != running:
            raise WellsStatementError(
                f"{stmt.source_pdf}: running balance {format_dollars(running)} "
                f"!= printed daily {format_dollars(txn.daily_balance_cents)} "
                f"on {txn.date.isoformat()} ({txn.payee})"
            )
    if running != stmt.ending_cents:
        raise WellsStatementError(
            f"{stmt.source_pdf}: transactions sum to {format_dollars(running)}, "
            f"statement ending is {format_dollars(stmt.ending_cents)}"
        )
    deposit_sum = sum(t.amount_cents for t in stmt.transactions if t.amount_cents > 0)
    withdraw_sum = sum(-t.amount_cents for t in stmt.transactions if t.amount_cents < 0)
    if deposit_sum != stmt.deposits_cents or withdraw_sum != stmt.withdrawals_cents:
        raise WellsStatementError(
            f"{stmt.source_pdf}: row totals "
            f"deposits {format_dollars(deposit_sum)} / "
            f"withdrawals {format_dollars(withdraw_sum)} "
            f"!= summary deposits {format_dollars(stmt.deposits_cents)} / "
            f"withdrawals {format_dollars(stmt.withdrawals_cents)}"
        )


def parse_wells_statement_pdf(path: Path, pages: list[list[TextItem]] | None = None) -> ParsedStatement:
    path = Path(path)
    page_items = pages if pages is not None else extract_pdf_items(path)
    header_date = _find_header_date(page_items)
    summary = _parse_summary(page_items, header_date)
    cols = _detect_columns(page_items)
    txns = _parse_history(
        page_items,
        cols,
        summary["period_start"],
        summary["period_end"],
        path.name,
    )
    stmt = ParsedStatement(
        source_pdf=path.name,
        product=summary["product"],
        period_start=summary["period_start"],
        period_end=summary["period_end"],
        beginning_cents=summary["beginning"],
        ending_cents=summary["ending"],
        deposits_cents=summary["deposits"],
        withdrawals_cents=summary["withdrawals"],
        transactions=txns,
        account_last4=summary["account_last4"],
    )
    _resolve_running_signs(stmt)
    _assert_running_balance(stmt)
    return stmt


def _normalize_payee(payee: str) -> str:
    return re.sub(r"\s+", " ", (payee or "").strip().upper())


def convert_wells_statement_uploads(
    files: Sequence[tuple[str, bytes]],
    bank_csvs: Sequence[tuple[str, bytes]] | None = None,
) -> ConvertResult:
    """Parse uploaded PDFs from memory. Writes a temp dir, then uses the path converter."""
    if not files:
        raise WellsStatementError("no PDF files given")
    used: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="wells-stmt-") as tmp:
        paths: list[Path] = []
        root = Path(tmp)
        for name, data in files:
            label = Path(name or "statement.pdf").name or "statement.pdf"
            if not data:
                raise WellsStatementError(f"{label}: file is empty")
            if not label.lower().endswith(".pdf"):
                label = f"{label}.pdf"
            dest_name = label
            n = 2
            while dest_name.lower() in used:
                dest_name = f"{Path(label).stem}-{n}{Path(label).suffix}"
                n += 1
            used.add(dest_name.lower())
            dest = root / dest_name
            dest.write_bytes(data)
            paths.append(dest)
        result = convert_wells_statements(paths)
    if bank_csvs:
        texts: list[tuple[str, str]] = []
        for name, data in bank_csvs:
            label = Path(name or "checking.csv").name or "checking.csv"
            if not data:
                raise WellsStatementError(f"{label}: file is empty")
            texts.append((label, data.decode("utf-8-sig", errors="replace")))
        result = merge_wells_bank_csvs(result, texts)
    return result


def convert_wells_statements(paths: Iterable[Path]) -> ConvertResult:
    path_list = [Path(p) for p in paths]
    if not path_list:
        raise WellsStatementError("no PDF paths given")
    parsed: list[ParsedStatement] = []
    errors: list[str] = []
    for path in path_list:
        try:
            parsed.append(parse_wells_statement_pdf(path))
        except WellsStatementError as exc:
            errors.append(str(exc))
    if errors:
        raise WellsStatementError(
            f"Failed {len(errors)} of {len(path_list)} PDFs:\n"
            + "\n".join(f"- {msg}" for msg in errors)
        )
    parsed.sort(key=lambda s: (s.period_start, s.source_pdf))
    warnings: list[str] = []
    unique: dict[tuple, ParsedStatement] = {}
    for stmt in parsed:
        key = (stmt.period_start, stmt.period_end, stmt.account_last4)
        if key in unique:
            warnings.append(f"duplicate period skipped: {stmt.source_pdf}")
            continue
        unique[key] = stmt
    parsed = list(unique.values())

    chain_errors: list[str] = []
    for left, right in zip(parsed, parsed[1:]):
        if left.account_last4 and right.account_last4 and left.account_last4 != right.account_last4:
            chain_errors.append(
                f"{left.source_pdf} and {right.source_pdf} look like different accounts"
            )
        if left.ending_cents != right.beginning_cents:
            chain_errors.append(
                f"chain break: {left.source_pdf} ending {format_dollars(left.ending_cents)} "
                f"!= {right.source_pdf} beginning {format_dollars(right.beginning_cents)}"
            )
        expected_next = left.period_end + timedelta(days=1)
        if right.period_start != expected_next:
            warnings.append(
                f"date gap after {left.source_pdf}: "
                f"{left.period_end.isoformat()} -> {right.period_start.isoformat()}"
            )
    if chain_errors:
        raise WellsStatementError(
            "Statement chain is incomplete:\n" + "\n".join(f"- {msg}" for msg in chain_errors)
        )

    txns: list[StatementTxn] = []
    seen: set[tuple] = set()
    for stmt in parsed:
        for txn in stmt.transactions:
            key = (txn.date, txn.amount_cents, _normalize_payee(txn.payee))
            if key in seen:
                continue
            seen.add(key)
            txns.append(txn)

    first = parsed[0]
    return ConvertResult(
        transactions=txns,
        opening_posted_cents=first.beginning_cents,
        opening_as_of=first.period_start,
        last_ending_cents=parsed[-1].ending_cents,
        last_ending_date=parsed[-1].period_end,
        statements=parsed,
        warnings=warnings,
    )


def _payees_close(left: str, right: str) -> bool:
    a = _normalize_payee(left)
    b = _normalize_payee(right)
    if not a or not b:
        return True
    if a == b:
        return True
    return a in b or b in a


def _claim_statement_match(
    date_value: date,
    amount_cents: int,
    payee: str,
    by_date_amount: dict[tuple, list[int]],
    txns: Sequence[StatementTxn],
    claimed: set[int],
) -> int | None:
    candidates = [
        idx for idx in by_date_amount.get((date_value, amount_cents), []) if idx not in claimed
    ]
    if not candidates:
        return None
    equal = [idx for idx in candidates if _normalize_payee(txns[idx].payee) == _normalize_payee(payee)]
    if equal:
        return equal[0]
    close = [idx for idx in candidates if _payees_close(txns[idx].payee, payee)]
    if close:
        return close[0]
    return None


def is_odysseus_setup_csv(text: str) -> bool:
    from integrations.finance.services.parsers import parse_csv_metadata

    meta, _body = parse_csv_metadata(text)
    source = (meta.get("source") or "").lower()
    return bool(meta.get("odysseus_finance") or source == "wells-statement-pdf")


def sniff_wells_bank_csv_text(text: str) -> bool:
    from integrations.finance.services.parsers import detect_csv_format

    if is_odysseus_setup_csv(text):
        return False
    try:
        return detect_csv_format(text) == "csv_wells_fargo"
    except ValueError:
        return False


def is_wells_bank_csv_filename(path: Path) -> bool:
    if path.suffix.lower() != ".csv":
        return False
    compact = path.name.lower().replace(" ", "").replace("_", "").replace("-", "")
    return "checking" in compact


def merge_wells_bank_csvs(
    result: ConvertResult,
    csvs: Sequence[tuple[str, str]],
) -> ConvertResult:
    """Keep statement rows for overlap. Append posted bank-export rows after the last statement."""
    from collections import defaultdict

    from integrations.finance.services.parsers import parse_wells_fargo_csv

    if not csvs:
        return result
    by_date_amount: dict[tuple, list[int]] = defaultdict(list)
    for idx, txn in enumerate(result.transactions):
        by_date_amount[(txn.date, txn.amount_cents)].append(idx)
    claimed: set[int] = set()
    appended: list[StatementTxn] = []
    matched = 0
    skipped_pending = 0
    skipped_overlap = 0
    names: list[str] = []
    cutoff = result.last_ending_date
    for name, text in csvs:
        label = Path(name or "checking.csv").name or "checking.csv"
        if not text.strip():
            raise WellsStatementError(f"{label}: file is empty")
        if is_odysseus_setup_csv(text):
            raise WellsStatementError(
                f"{label}: this is a statement setup file, not a bank export CSV"
            )
        if not sniff_wells_bank_csv_text(text):
            raise WellsStatementError(
                f"{label}: not a Wells Fargo checking CSV (need DATE, DESCRIPTION, AMOUNT)"
            )
        names.append(label)
        parsed = parse_wells_fargo_csv(text)
        for tx in parsed.transactions:
            status = ""
            if tx.raw:
                status = (tx.raw.get("STATUS") or tx.raw.get("Status") or "").strip().lower()
            if status == "pending":
                skipped_pending += 1
                continue
            hit = _claim_statement_match(
                tx.date,
                tx.amount_cents,
                tx.payee,
                by_date_amount,
                result.transactions,
                claimed,
            )
            if hit is not None:
                claimed.add(hit)
                matched += 1
                continue
            if tx.date <= cutoff:
                skipped_overlap += 1
                continue
            appended.append(
                StatementTxn(
                    date=tx.date,
                    amount_cents=tx.amount_cents,
                    payee=tx.payee,
                    check_number=tx.check_number,
                    daily_balance_cents=None,
                    source_pdf=label,
                    statement_start=None,
                    statement_end=None,
                )
            )
    numbered = [(txn.date, 0, idx, txn) for idx, txn in enumerate(result.transactions)]
    numbered.extend((txn.date, 1, idx, txn) for idx, txn in enumerate(appended))
    numbered.sort()
    result.transactions = [txn for _date, _kind, _idx, txn in numbered]
    result.bank_csv_names = names
    result.bank_matched_count = matched
    result.bank_appended_count = len(appended)
    result.bank_skipped_pending_count = skipped_pending
    result.bank_skipped_overlap_count = skipped_overlap
    if names:
        result.warnings.append(
            f"Bank export {', '.join(names)}: kept {matched} overlapping posted rows from statements, "
            f"added {len(appended)} newer posted rows, skipped {skipped_pending} pending, "
            f"skipped {skipped_overlap} extra overlap rows"
        )
    return result


def transactions_to_csv(txns: Sequence[StatementTxn]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "DATE",
            "DESCRIPTION",
            "AMOUNT",
            "CHECK #",
            "DAILY_BALANCE",
            "STATEMENT_START",
            "STATEMENT_END",
            "SOURCE_PDF",
        ]
    )
    for txn in txns:
        daily = "" if txn.daily_balance_cents is None else format_cents(txn.daily_balance_cents)
        start = txn.statement_start.isoformat() if txn.statement_start else ""
        end = txn.statement_end.isoformat() if txn.statement_end else ""
        writer.writerow(
            [
                txn.date.strftime("%m/%d/%Y"),
                txn.payee,
                format_cents(txn.amount_cents),
                txn.check_number or "",
                daily,
                start,
                end,
                txn.source_pdf,
            ]
        )
    return buf.getvalue()


def result_to_csv(result: ConvertResult) -> str:
    product = ""
    if result.statements and result.statements[0].product:
        product = result.statements[0].product
    header = "\n".join(
        [
            "# odysseus-finance: v1",
            "# source: wells-statement-pdf",
            f"# opening_posted: {format_cents(result.opening_posted_cents)}",
            f"# opening_as_of: {result.opening_as_of.isoformat()}",
            f"# last_ending: {format_cents(result.last_ending_cents)}",
            f"# last_ending_date: {result.last_ending_date.isoformat()}",
            f"# statement_count: {len(result.statements)}",
            f"# transaction_count: {len(result.transactions)}",
            f"# product: {product}",
            f"# bank_csv: {', '.join(result.bank_csv_names)}" if result.bank_csv_names else "# bank_csv:",
            f"# bank_appended: {result.bank_appended_count}",
        ]
    )
    return header + "\n" + transactions_to_csv(result.transactions)


def format_convert_report(result: ConvertResult) -> str:
    lines = [
        f"Statements: {len(result.statements)}",
        f"Transactions: {len(result.transactions)}",
        f"Opening posted: {format_dollars(result.opening_posted_cents)}",
        f"Balance as of: {result.opening_as_of.isoformat()}",
        f"Last statement ending: {format_dollars(result.last_ending_cents)} on {result.last_ending_date.isoformat()}",
        "",
        "This CSV includes opening posted. Import it in Finance and apply opening posted",
        "when the account is empty. Overlap with a later bank CSV stays on the statement rows.",
    ]
    if result.bank_csv_names:
        lines.append(
            f"Bank export: {', '.join(result.bank_csv_names)}. "
            f"Added {result.bank_appended_count} newer posted rows after the last statement. "
            f"Newer bank-export rows have no daily balance."
        )
    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        lines.extend(f"- {w}" for w in result.warnings)
    lines.append("")
    lines.append("Per statement:")
    for stmt in result.statements:
        product = f" {stmt.product}" if stmt.product else ""
        lines.append(
            f"- {stmt.source_pdf}{product}: {stmt.period_start.isoformat()} to "
            f"{stmt.period_end.isoformat()}  "
            f"{format_dollars(stmt.beginning_cents)} -> {format_dollars(stmt.ending_cents)}  "
            f"({len(stmt.transactions)} rows)"
        )
    return "\n".join(lines) + "\n"


def suggested_account_fields(result: ConvertResult) -> dict:
    """Fill a new Finance account from statement metadata. User can edit the rest."""
    stmt = result.statements[0] if result.statements else None
    product = (stmt.product or "").strip() if stmt else ""
    last4s = {s.account_last4 for s in (result.statements or []) if s.account_last4}
    last4 = next(iter(last4s)) if len(last4s) == 1 else None
    lower = product.lower()
    account_type = "savings" if "saving" in lower else "checking"
    return {
        "name": (product or "Wells Fargo Checking")[:200],
        "institution": "Wells Fargo",
        "account_type": account_type,
        "purpose": "operating",
        "opening_balance_cents": result.opening_posted_cents,
        "opening_balance_date": result.opening_as_of.isoformat() if result.opening_as_of else None,
        "mask_last4": last4,
    }


def is_wells_statement_filename(path: Path) -> bool:
    name = path.name.lower().replace(" ", "").replace("_", "")
    return path.suffix.lower() == ".pdf" and "wellsfargo" in name


def expand_pdf_inputs(raw_paths: Sequence[str | Path]) -> list[Path]:
    pdfs, _csvs = expand_convert_inputs(raw_paths)
    return pdfs


def expand_convert_inputs(raw_paths: Sequence[str | Path]) -> tuple[list[Path], list[Path]]:
    pdfs: list[Path] = []
    csvs: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if path.is_dir():
            found_pdfs = sorted(p for p in path.iterdir() if is_wells_statement_filename(p))
            if not found_pdfs:
                raise WellsStatementError(f"no Wells Fargo statement PDFs in {path}")
            pdfs.extend(found_pdfs)
            csvs.extend(
                sorted(
                    p
                    for p in path.iterdir()
                    if is_wells_bank_csv_filename(p) and sniff_wells_bank_csv_text(
                        p.read_text(encoding="utf-8-sig", errors="replace")
                    )
                )
            )
        elif path.is_file() and path.suffix.lower() == ".pdf":
            pdfs.append(path)
        elif path.is_file() and path.suffix.lower() == ".csv":
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if not sniff_wells_bank_csv_text(text):
                raise WellsStatementError(
                    f"{path.name}: not a Wells Fargo checking CSV (need DATE, DESCRIPTION, AMOUNT)"
                )
            csvs.append(path)
        elif path.is_file():
            raise WellsStatementError(f"{path.name}: expected a statement PDF or Wells checking CSV")
        else:
            raise WellsStatementError(f"not found: {path}")
    if not pdfs:
        raise WellsStatementError("no PDF files")
    return pdfs, csvs
