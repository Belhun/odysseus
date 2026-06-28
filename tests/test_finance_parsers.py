"""Finance plugin parser tests."""

from pathlib import Path

import pytest

from integrations.finance.services.parsers import (
    detect_csv_format,
    parse_navy_federal_csv,
    parse_wells_fargo_csv,
    parse_upload,
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
    rows = parse_wells_fargo_csv(WELLS_FARGO_SAMPLE)
    assert len(rows) == 2
    assert rows[0].amount_cents == -985
    assert rows[1].amount_cents == 150000


@pytest.mark.area_routes
def test_parse_navy_federal_debit_credit_indicator():
    rows = parse_navy_federal_csv(NAVY_FEDERAL_SAMPLE)
    assert len(rows) == 2
    assert rows[0].amount_cents == -3119
    assert rows[1].amount_cents == 2800


@pytest.mark.area_routes
@pytest.mark.skipif(not (PRIVATE_DIR / "wells_fargo_Checking_e719.csv").exists(), reason="private fixture missing")
def test_parse_real_wells_fargo_export():
    content = (PRIVATE_DIR / "wells_fargo_Checking_e719.csv").read_bytes()
    fmt, rows = parse_upload("wells_fargo.csv", content)
    assert fmt == "csv_wells_fargo"
    assert len(rows) > 100


@pytest.mark.area_routes
@pytest.mark.skipif(not (PRIVATE_DIR / "Navy_fed_Main_bussness_transactions_167a.csv").exists(), reason="private fixture missing")
def test_parse_real_navy_federal_export():
    content = (PRIVATE_DIR / "Navy_fed_Main_bussness_transactions_167a.csv").read_bytes()
    fmt, rows = parse_upload("nfcu.csv", content)
    assert fmt == "csv_navy_federal"
    assert len(rows) > 10
