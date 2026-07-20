"""Money helper parity with desktop MoneyHelpersTests."""

from decimal import Decimal

import pytest

from integrations.sysforge.db import money


@pytest.mark.area_routes
def test_to_cents_from_cents_round_trip_10_99():
    dollars = Decimal("10.99")
    cents = money.to_cents(dollars)
    assert cents == 1099
    assert money.from_cents(cents) == dollars


@pytest.mark.area_routes
def test_to_cents_rounds_away_from_zero_10_995():
    assert money.to_cents(Decimal("10.995")) == 1100


@pytest.mark.area_routes
def test_to_basis_points_round_trip_7_25():
    percent = Decimal("7.25")
    bps = money.to_basis_points(percent)
    assert bps == 725
    assert money.from_basis_points(bps) == percent


@pytest.mark.area_routes
def test_to_milliunits_round_trip_2_5():
    qty = Decimal("2.5")
    mu = money.to_milliunits(qty)
    assert mu == 2500
    assert money.from_milliunits(mu) == qty


@pytest.mark.area_routes
def test_calculate_tax_cents_zero_rate():
    assert money.calculate_tax_cents(10_000, 0) == 0


@pytest.mark.area_routes
def test_calculate_tax_cents_known_rate():
    # $100.00 @ 7.25% = $7.25
    assert money.calculate_tax_cents(10_000, 725) == 725


@pytest.mark.area_routes
def test_calculate_line_total_percent_discount():
    # 1 unit @ $50, 10% off => $45
    assert money.calculate_line_total_cents(1000, 5000, "Percent", 1000) == 4500


@pytest.mark.area_routes
def test_calculate_line_total_amount_discount():
    # 1 unit @ $50, $5 off => $45
    assert money.calculate_line_total_cents(1000, 5000, "Amount", 500) == 4500
