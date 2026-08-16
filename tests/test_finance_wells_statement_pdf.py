"""Wells Fargo statement PDF converter tests (synthetic layout + optional live PDFs)."""

from datetime import date
from pathlib import Path

import pytest

from integrations.finance.services.parsers import parse_csv_metadata, parse_upload, parse_wells_fargo_csv
from integrations.finance.services.wells_statement_pdf import (
    ColumnXs,
    TextItem,
    WellsStatementError,
    classify_amount_column,
    convert_wells_statements,
    format_cents,
    parse_money_cents,
    parse_wells_statement_pdf,
    result_to_csv,
    transactions_to_csv,
)

JAN_PDF = Path(r"c:\Users\Belhun\Downloads\011019 WellsFargo.pdf")
SEP_PDF = Path(r"c:\Users\Belhun\Downloads\090821 WellsFargo.pdf")
JULY_PDF = Path(r"c:\Users\Belhun\Downloads\070824 WellsFargo.pdf")
AUG_PDF = Path(r"c:\Users\Belhun\Downloads\080724 WellsFargo.pdf")


def T(x: float, y: float, text: str) -> TextItem:
    return TextItem(x=x, y=y, text=text)


def _summary_page(
    *,
    header: str,
    begin_md: str,
    end_md: str,
    beginning: str,
    deposits: str,
    withdrawals: str,
    ending: str,
    fee_period: str,
    product: str = "Wells Fargo Everyday Checking",
) -> list[TextItem]:
    return [
        T(48, 1001, product),
        T(48, 984, header),
        T(48, 289, "Statement period activity summary"),
        T(86, 272, f"Beginning balance on {begin_md}"),
        T(401, 272, beginning),
        T(86, 256, "Deposits/Additions"),
        T(399, 256, deposits),
        T(86, 240, "Withdrawals/Subtractions"),
        T(392, 240, withdrawals),
        T(86, 221, f"Ending balance on {end_md}"),
        T(400, 221, ending),
        T(81, 491, fee_period),
    ]


def _history_headers(y: float = 890) -> list[TextItem]:
    return [
        T(48, y + 13, "Transaction history"),
        T(539, y, "Deposits/"),
        T(611, y, "Withdrawals/"),
        T(700, y, "Ending daily"),
        T(82, y - 13, "Date"),
        T(200, y - 13, "Description"),
        T(538, y - 13, "Additions"),
        T(616, y - 13, "Subtractions"),
        T(720, y - 13, "balance"),
    ]


def _txn(
    y: float,
    md: str,
    desc: str,
    *,
    deposit: str | None = None,
    withdraw: str | None = None,
    daily: str | None = None,
    cont: str | None = None,
    check: str | None = None,
) -> list[TextItem]:
    items = [T(82, y, md), T(200, y, desc)]
    if check:
        items.append(T(156, y, check))
    if deposit:
        items.append(T(549, y, deposit))
    if withdraw:
        items.append(T(646, y, withdraw))
    if daily:
        items.append(T(725, y, daily))
    if cont:
        items.append(T(200, y - 12, cont))
    return items


def _history_close(y: float, end_md: str, ending: str, dep_total: str, wd_total: str) -> list[TextItem]:
    return [
        T(82, y, f"Ending balance on {end_md}"),
        T(724, y, ending),
        T(82, y - 23, "Totals"),
        T(533, y - 23, dep_total),
        T(624, y - 23, wd_total),
        T(81, y - 45, "The Ending Daily Balance does not reflect any pending withdrawals"),
    ]


def january_statement_pages() -> list[list[TextItem]]:
    """$100.00 start; coffee -$10; payroll +$50; fee -$15; end $125.00."""
    summary = _summary_page(
        header="January 31, 2024",
        begin_md="1/1",
        end_md="1/31",
        beginning="$100.00",
        deposits="50.00",
        withdrawals="-  25.00",
        ending="$125.00",
        fee_period="Fee period 01/01/2024 - 01/31/2024",
    )
    history = (
        _history_headers()
        + _txn(830, "1/5", "Purchase authorized on 01/04 Test Cafe", withdraw="10.00", daily="90.00", cont="Card 5050")
        + _txn(790, "1/10", "Direct Deposit Employer", deposit="50.00", daily="140.00")
        + _txn(760, "1/31", "Monthly Service Fee", withdraw="15.00", daily="125.00")
        + _history_close(720, "1/31", "125.00", "$50.00", "$25.00")
    )
    return [summary, history]


def february_statement_pages() -> list[list[TextItem]]:
    """Chains from January: begin $125; grocery -$25; end $100.00."""
    summary = _summary_page(
        header="February 29, 2024",
        begin_md="2/1",
        end_md="2/29",
        beginning="$125.00",
        deposits="0.00",
        withdrawals="-  25.00",
        ending="$100.00",
        fee_period="Fee period 02/01/2024 - 02/29/2024",
    )
    history = (
        _history_headers()
        + _txn(830, "2/3", "Purchase authorized on 02/02 Grocery", withdraw="25.00", daily="100.00")
        + _history_close(780, "2/29", "100.00", "$0.00", "$25.00")
    )
    return [summary, history]


@pytest.mark.area_routes
def test_parse_money_and_column_classify():
    assert parse_money_cents("$474.63") == 47463
    assert parse_money_cents("-  3,780.44") == -378044
    assert parse_money_cents("1,290.00") == 129000
    cols = ColumnXs(deposit=539, withdraw=611, balance=700)
    assert classify_amount_column(549, cols) == "deposit"
    assert classify_amount_column(646, cols) == "withdraw"
    assert classify_amount_column(632, cols) == "withdraw"
    assert classify_amount_column(725, cols) == "balance"


@pytest.mark.area_routes
def test_parse_synthetic_statement_running_balance():
    stmt = parse_wells_statement_pdf(Path("jan.pdf"), pages=january_statement_pages())
    assert stmt.beginning_cents == 10000
    assert stmt.ending_cents == 12500
    assert stmt.period_start == date(2024, 1, 1)
    assert stmt.period_end == date(2024, 1, 31)
    assert [t.amount_cents for t in stmt.transactions] == [-1000, 5000, -1500]
    assert stmt.transactions[0].payee.endswith("Card 5050")
    assert stmt.transactions[0].daily_balance_cents == 9000
    assert stmt.transactions[2].payee == "Monthly Service Fee"


@pytest.mark.area_routes
def test_check_number_and_csv_round_trip():
    summary = _summary_page(
        header="March 31, 2024",
        begin_md="3/1",
        end_md="3/31",
        beginning="$50.00",
        deposits="0.00",
        withdrawals="-  12.00",
        ending="$38.00",
        fee_period="Fee period 03/01/2024 - 03/31/2024",
    )
    history = (
        _history_headers()
        + _txn(830, "3/4", "Check paid", withdraw="12.00", daily="38.00", check="1022")
        + _history_close(780, "3/31", "38.00", "$0.00", "$12.00")
    )
    stmt = parse_wells_statement_pdf(Path("mar.pdf"), pages=[summary, history])
    assert stmt.transactions[0].check_number == "1022"
    csv_text = transactions_to_csv(stmt.transactions)
    parsed = parse_wells_fargo_csv(csv_text)
    assert parsed.errors == []
    assert parsed.transactions[0].amount_cents == -1200
    assert parsed.transactions[0].check_number == "1022"
    assert parsed.transactions[0].daily_balance_cents == 3800
    assert parsed.transactions[0].statement_start == date(2024, 3, 1)


@pytest.mark.area_routes
def test_year_wrap_assigns_december_to_prior_year():
    summary = _summary_page(
        header="January 7, 2025",
        begin_md="12/8",
        end_md="1/7",
        beginning="$10.00",
        deposits="5.00",
        withdrawals="-  1.00",
        ending="$14.00",
        fee_period="Fee period 12/08/2024 - 01/07/2025",
    )
    history = (
        _history_headers()
        + _txn(830, "12/20", "Direct Deposit", deposit="5.00", daily="15.00")
        + _txn(800, "1/3", "Purchase snack", withdraw="1.00", daily="14.00")
        + _history_close(760, "1/7", "14.00", "$5.00", "$1.00")
    )
    stmt = parse_wells_statement_pdf(Path("wrap.pdf"), pages=[summary, history])
    assert stmt.period_start == date(2024, 12, 8)
    assert stmt.transactions[0].date == date(2024, 12, 20)
    assert stmt.transactions[1].date == date(2025, 1, 3)


@pytest.mark.area_routes
def test_chain_two_statements_opening_posted(tmp_path, monkeypatch):
    from integrations.finance.services import wells_statement_pdf as mod

    def fake_extract(path: Path):
        name = Path(path).name
        if name.startswith("jan"):
            return january_statement_pages()
        if name.startswith("feb"):
            return february_statement_pages()
        raise AssertionError(name)

    monkeypatch.setattr(mod, "extract_pdf_items", fake_extract)
    jan = tmp_path / "jan.pdf"
    feb = tmp_path / "feb.pdf"
    jan.write_bytes(b"%PDF")
    feb.write_bytes(b"%PDF")
    result = convert_wells_statements([feb, jan])
    assert result.opening_posted_cents == 10000
    assert result.opening_as_of == date(2024, 1, 1)
    assert result.last_ending_cents == 10000
    assert result.last_ending_date == date(2024, 2, 29)
    assert [t.date for t in result.transactions] == [
        date(2024, 1, 5),
        date(2024, 1, 10),
        date(2024, 1, 31),
        date(2024, 2, 3),
    ]


def orphan_statement_pages() -> list[list[TextItem]]:
    """Valid internally, does not chain from January."""
    summary = _summary_page(
        header="February 29, 2024",
        begin_md="2/1",
        end_md="2/29",
        beginning="$50.00",
        deposits="0.00",
        withdrawals="-  10.00",
        ending="$40.00",
        fee_period="Fee period 02/01/2024 - 02/29/2024",
    )
    history = (
        _history_headers()
        + _txn(830, "2/3", "Purchase authorized on 02/02 Snack", withdraw="10.00", daily="40.00")
        + _history_close(780, "2/29", "40.00", "$0.00", "$10.00")
    )
    return [summary, history]


@pytest.mark.area_routes
def test_chain_break_raises(tmp_path, monkeypatch):
    from integrations.finance.services import wells_statement_pdf as mod

    def fake_extract(path: Path):
        if Path(path).name.startswith("jan"):
            return january_statement_pages()
        return orphan_statement_pages()

    monkeypatch.setattr(mod, "extract_pdf_items", fake_extract)
    jan = tmp_path / "jan.pdf"
    feb = tmp_path / "feb.pdf"
    jan.write_bytes(b"%PDF")
    feb.write_bytes(b"%PDF")
    with pytest.raises(WellsStatementError, match="chain break"):
        convert_wells_statements([jan, feb])


@pytest.mark.area_routes
def test_skips_fee_summary_after_history():
    pages = january_statement_pages()
    pages[1].extend(
        [
            T(48, 100, "Monthly service fee summary"),
            T(646, 80, "10.00"),
            T(82, 80, "1/15"),
            T(200, 80, "Should not import"),
        ]
    )
    stmt = parse_wells_statement_pdf(Path("jan.pdf"), pages=pages)
    assert all("Should not import" not in t.payee for t in stmt.transactions)
    assert any(t.payee == "Monthly Service Fee" for t in stmt.transactions)


@pytest.mark.area_routes
@pytest.mark.skipif(not (JULY_PDF.exists() and AUG_PDF.exists()), reason="local Wells PDFs missing")
def test_live_july_august_statements_chain():
    result = convert_wells_statements([JULY_PDF, AUG_PDF])
    assert result.opening_posted_cents == 4070
    assert result.opening_as_of == date(2024, 6, 8)
    assert result.last_ending_cents == 63681
    assert result.statements[0].ending_cents == 47463
    assert result.statements[1].beginning_cents == 47463
    harrys = [t for t in result.transactions if "Harrys Sports Bar" in t.payee]
    assert len(harrys) == 1
    assert harrys[0].amount_cents == -5000
    assert harrys[0].daily_balance_cents == 84221
    csv_text = transactions_to_csv(result.transactions)
    parsed = parse_wells_fargo_csv(csv_text)
    assert parsed.errors == []
    assert len(parsed.transactions) == len(result.transactions)
    assert format_cents(result.opening_posted_cents) == "40.70"


def packed_statement_pages() -> list[list[TextItem]]:
    summary = [
        T(40.3, 744.7, "Wells Fargo Everyday Checking"),
        T(188.4, 729.8, "December 12, 2018 - January 10, 2019"),
        T(40.1, 283.7, "Activity summary"),
        T(64.8, 271.2, "Beginning balance on 12/12 $100.00"),
        T(64.8, 259.2, "Deposits/Additions 50.00"),
        T(64.8, 247.2, "Withdrawals/Subtractions -  25.00"),
        T(64.8, 232.8, "Ending balance on 1/10  $125.00"),
    ]
    history = [
        T(40.1, 670.1, "Transaction history"),
        T(127.4, 643.0, "Check Deposits/ Withdrawals/ Ending daily"),
        T(64.8, 633.4, "Date Number Description Additions Subtractions balance"),
        T(64.8, 623.3, "12/12 Purchase authorized on 12/10 Test Cafe"),
        T(487.4, 623.3, "25.00 75.00"),
        T(64.8, 600.0, "1/3 Direct Deposit Employer"),
        T(418.6, 600.0, "50.00"),
        T(520.0, 600.0, "125.00"),
        T(64.8, 560.0, "Ending balance on 1/10 125.00"),
        T(64.8, 540.0, "Totals $50.00 $25.00"),
    ]
    return [summary, history]


@pytest.mark.area_routes
def test_packed_2019_layout_and_odysseus_csv_header(tmp_path, monkeypatch):
    from integrations.finance.services import wells_statement_pdf as mod

    monkeypatch.setattr(mod, "extract_pdf_items", lambda _path: packed_statement_pages())
    pdf = tmp_path / "011019 WellsFargo.pdf"
    pdf.write_bytes(b"%PDF")
    result = convert_wells_statements([pdf])
    assert result.opening_posted_cents == 10000
    assert result.opening_as_of == date(2018, 12, 12)
    assert [t.amount_cents for t in result.transactions] == [-2500, 5000]
    csv_text = result_to_csv(result)
    meta, _body = parse_csv_metadata(csv_text)
    assert meta["odysseus_finance"] == "v1"
    assert meta["opening_posted"] == "100.00"
    assert meta["opening_as_of"] == "2018-12-12"
    fmt, rows, errors, extra = parse_upload("wells-from-statements.csv", csv_text.encode("utf-8"))
    assert fmt == "csv_wells_fargo"
    assert errors == []
    assert extra["opening_posted_cents"] == 10000
    assert extra["opening_as_of"] == "2018-12-12"
    assert len(rows) == 2
    assert rows[0].daily_balance_cents is not None
    assert rows[0].statement_start.isoformat() == "2018-12-12"
    assert rows[0].source_statement == "011019 WellsFargo.pdf"


@pytest.mark.area_routes
def test_convert_uploads_uses_original_filenames(tmp_path, monkeypatch):
    from integrations.finance.services import wells_statement_pdf as mod
    from integrations.finance.services.wells_statement_pdf import convert_wells_statement_uploads

    def fake_extract(path):
        name = Path(path).name
        if name.startswith("jan"):
            return january_statement_pages()
        if name.startswith("feb"):
            return february_statement_pages()
        raise AssertionError(name)

    monkeypatch.setattr(mod, "extract_pdf_items", fake_extract)
    result = convert_wells_statement_uploads(
        [("jan.pdf", b"%PDF"), ("feb.pdf", b"%PDF")]
    )
    assert result.opening_posted_cents == 10000
    assert len(result.transactions) == 4
    assert {t.source_pdf for t in result.transactions} == {"jan.pdf", "feb.pdf"}


BANK_CHECKING_CSV = '''"DATE","DESCRIPTION","AMOUNT","CHECK #","STATUS"
"01/05/2024","Test Cafe","-10.00","","Posted"
"01/05/2024","Test Cafe","-10.00","","Posted"
"01/10/2024","Direct Deposit Employer","50.00","","Posted"
"01/31/2024","Monthly Service Fee","-15.00","","Posted"
"02/05/2024","New Merchant","-3.00","","Posted"
"02/06/2024","Pending Coffee","-4.00","","Pending"
'''


@pytest.mark.area_routes
def test_merge_checking_csv_keeps_statement_overlap_and_appends_newer(tmp_path, monkeypatch):
    from integrations.finance.services import wells_statement_pdf as mod
    from integrations.finance.services.wells_statement_pdf import (
        convert_wells_statement_uploads,
        is_wells_bank_csv_filename,
        merge_wells_bank_csvs,
    )

    def fake_extract(path):
        name = Path(path).name
        if name.startswith("jan"):
            return january_statement_pages()
        raise AssertionError(name)

    monkeypatch.setattr(mod, "extract_pdf_items", fake_extract)
    assert is_wells_bank_csv_filename(Path("checking.csv"))
    assert is_wells_bank_csv_filename(Path("Wells fargo Checking.csv"))
    assert not is_wells_bank_csv_filename(Path("wells-from-statements.csv"))

    result = convert_wells_statement_uploads([("jan.pdf", b"%PDF")])
    assert len(result.transactions) == 3
    cafe = next(t for t in result.transactions if t.amount_cents == -1000)
    assert cafe.daily_balance_cents == 9000

    merged = merge_wells_bank_csvs(result, [("checking.csv", BANK_CHECKING_CSV)])
    assert merged.bank_matched_count == 3
    assert merged.bank_appended_count == 1
    assert merged.bank_skipped_pending_count == 1
    assert merged.bank_skipped_overlap_count == 1
    assert len(merged.transactions) == 4
    still_cafe = next(t for t in merged.transactions if t.amount_cents == -1000)
    assert still_cafe.daily_balance_cents == 9000
    assert "Test Cafe" in still_cafe.payee
    assert still_cafe.source_pdf == "jan.pdf"
    newest = merged.transactions[-1]
    assert newest.date == date(2024, 2, 5)
    assert newest.amount_cents == -300
    assert newest.daily_balance_cents is None
    assert newest.source_pdf == "checking.csv"


@pytest.mark.area_routes
def test_folder_picks_checking_csv_without_wells_in_filename(tmp_path, monkeypatch):
    from integrations.finance.services import wells_statement_pdf as mod
    from integrations.finance.services.wells_statement_pdf import expand_convert_inputs

    def fake_extract(path):
        return january_statement_pages()

    monkeypatch.setattr(mod, "extract_pdf_items", fake_extract)
    folder = tmp_path / "stmts"
    folder.mkdir()
    (folder / "011019 WellsFargo.pdf").write_bytes(b"%PDF")
    (folder / "checking.csv").write_text(BANK_CHECKING_CSV, encoding="utf-8")
    (folder / "notes.csv").write_text("foo,bar\n1,2\n", encoding="utf-8")
    pdfs, csvs = expand_convert_inputs([folder])
    assert [p.name for p in pdfs] == ["011019 WellsFargo.pdf"]
    assert [p.name for p in csvs] == ["checking.csv"]


@pytest.mark.area_routes
@pytest.mark.skipif(not JAN_PDF.exists(), reason="local 2019 Wells PDF missing")
def test_live_2019_packed_statement():
    stmt = parse_wells_statement_pdf(JAN_PDF)
    assert stmt.period_start == date(2018, 12, 12)
    assert stmt.period_end == date(2019, 1, 10)
    assert stmt.beginning_cents == 10414
    assert stmt.ending_cents == 9988


@pytest.mark.area_routes
@pytest.mark.skipif(not SEP_PDF.exists(), reason="local 2021 Wells PDF missing")
def test_live_2021_negative_ending():
    stmt = parse_wells_statement_pdf(SEP_PDF)
    assert stmt.period_start == date(2021, 8, 7)
    assert stmt.ending_cents == -4478
    assert any("Overdraft Fee" in t.payee for t in stmt.transactions)
