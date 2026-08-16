"""Finance plugin parser tests."""

from pathlib import Path

import pytest

from integrations.finance.services.parsers import (
    detect_csv_format,
    parse_navy_federal_csv,
    parse_ofx_qfx,
    parse_upload,
    parse_wells_fargo_csv,
)
from tests.fixtures.finance.synthetic_samples import NAVY_FEDERAL_SAMPLE, WELLS_FARGO_SAMPLE

PRIVATE_DIR = Path(__file__).resolve().parent / "fixtures" / "finance" / "private"


@pytest.mark.area_routes
def test_detect_wells_fargo_format():
    assert detect_csv_format(WELLS_FARGO_SAMPLE) == "csv_wells_fargo"


@pytest.mark.area_routes
def test_detect_navy_federal_format():
    assert detect_csv_format(NAVY_FEDERAL_SAMPLE) == "csv_navy_federal"


@pytest.mark.area_routes
def test_parse_wells_fargo_signed_amounts():
    result = parse_wells_fargo_csv(WELLS_FARGO_SAMPLE)
    rows = result.transactions
    assert len(rows) == 2
    assert rows[0].amount_cents == -985
    assert rows[1].amount_cents == 150000
    assert result.errors == []


@pytest.mark.area_routes
def test_parse_navy_federal_debit_credit_indicator():
    result = parse_navy_federal_csv(NAVY_FEDERAL_SAMPLE)
    rows = result.transactions
    assert len(rows) == 2
    assert rows[0].amount_cents == -3119
    assert rows[1].amount_cents == 2800


@pytest.mark.area_routes
def test_csv_parser_skips_bad_rows_and_reports_errors():
    csv_text = """DATE,AMOUNT,DESCRIPTION
01/15/2024,-9.85,GROCERY
bad-date,10.00,BROKEN
01/16/2024,1500.00,PAYCHECK
"""
    result = parse_wells_fargo_csv(csv_text)
    assert len(result.transactions) == 2
    assert len(result.errors) == 1
    assert result.errors[0].row == 2


@pytest.mark.area_routes
def test_parse_wells_statement_setup_extra_columns():
    csv_text = """DATE,DESCRIPTION,AMOUNT,CHECK #,DAILY_BALANCE,STATEMENT_START,STATEMENT_END,SOURCE_PDF
01/05/2024,Test Cafe,-10.00,,90.00,2024-01-01,2024-01-31,jan.pdf
"""
    result = parse_wells_fargo_csv(csv_text)
    assert result.errors == []
    tx = result.transactions[0]
    assert tx.amount_cents == -1000
    assert tx.daily_balance_cents == 9000
    assert tx.statement_start.isoformat() == "2024-01-01"
    assert tx.statement_end.isoformat() == "2024-01-31"
    assert tx.source_statement == "jan.pdf"
    with pytest.raises(ValueError, match="empty"):
        parse_upload("data.csv", b"")


@pytest.mark.area_routes
def test_parse_ofx_garbage_raises_value_error():
    with pytest.raises(ValueError, match="OFX"):
        parse_ofx_qfx(b"<not>valid</not>")

@pytest.mark.area_routes
@pytest.mark.skipif(not (PRIVATE_DIR / "wells_fargo_Checking_e719.csv").exists(), reason="private fixture missing")
def test_parse_real_wells_fargo_export():
    content = (PRIVATE_DIR / "wells_fargo_Checking_e719.csv").read_bytes()
    fmt, rows, errors, _extra = parse_upload("wells_fargo.csv", content)
    assert fmt == "csv_wells_fargo"
    assert len(rows) > 100
    assert errors == []


@pytest.mark.area_routes
@pytest.mark.skipif(not (PRIVATE_DIR / "Navy_fed_Main_bussness_transactions_167a.csv").exists(), reason="private fixture missing")
def test_parse_real_navy_federal_export():
    content = (PRIVATE_DIR / "Navy_fed_Main_bussness_transactions_167a.csv").read_bytes()
    fmt, rows, errors, _extra = parse_upload("nfcu.csv", content)
    assert fmt == "csv_navy_federal"
    assert len(rows) > 10
    assert errors == []
