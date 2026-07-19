"""Money helpers: dollars ↔ cents, percent ↔ bps, quantity ↔ milliunits.

Mirrors SysForge Helpers/MoneyHelpers.cs (MidpointRounding.AwayFromZero).
Never use float for money math — Decimal only.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS_PER_DOLLAR = 100
BASIS_POINTS_PER_PERCENT = 100
MILLIUNITS_PER_UNIT = 1000

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


def _as_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _round_away(value: Decimal) -> Decimal:
    """Round half away from zero (C# MidpointRounding.AwayFromZero)."""
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def to_cents(dollars: Decimal | int | str) -> int:
    """Convert dollars to integer cents. $10.99 → 1099."""
    return int(_round_away(_as_decimal(dollars) * CENTS_PER_DOLLAR))


def from_cents(cents: int) -> Decimal:
    """Convert cents to dollars. 1099 → 10.99."""
    return Decimal(cents) / CENTS_PER_DOLLAR


def to_basis_points(percent: Decimal | int | str) -> int:
    """Convert percent to basis points. 7.25% → 725."""
    return int(_round_away(_as_decimal(percent) * BASIS_POINTS_PER_PERCENT))


def from_basis_points(basis_points: int) -> Decimal:
    """Convert basis points to percent. 725 → 7.25."""
    return Decimal(basis_points) / BASIS_POINTS_PER_PERCENT


def to_milliunits(quantity: Decimal | int | str) -> int:
    """Convert quantity to milliunits. 2.5 → 2500."""
    return int(_round_away(_as_decimal(quantity) * MILLIUNITS_PER_UNIT))


def from_milliunits(milliunits: int) -> Decimal:
    """Convert milliunits to quantity. 2500 → 2.5."""
    return Decimal(milliunits) / MILLIUNITS_PER_UNIT


def calculate_tax_cents(subtotal_cents: int, rate_basis_points: int) -> int:
    """Tax in cents from subtotal cents and rate in basis points."""
    subtotal = from_cents(subtotal_cents)
    rate = from_basis_points(rate_basis_points) / _HUNDRED
    return to_cents(subtotal * rate)


def calculate_line_total_cents(
    quantity_milliunits: int,
    unit_price_cents: int,
    discount_type: str | None,
    discount_value: int,
) -> int:
    """Line total in cents: (qty × unit) − discount.

    discount_type: None / other → no discount;
    ``Percent`` → discount_value is basis points;
    ``Amount`` → discount_value is cents.
    """
    quantity = from_milliunits(quantity_milliunits)
    unit_price = from_cents(unit_price_cents)
    base_amount = quantity * unit_price

    if discount_type == "Percent":
        discount = base_amount * (from_basis_points(int(discount_value)) / _HUNDRED)
    elif discount_type == "Amount":
        discount = from_cents(discount_value)
    else:
        discount = _ZERO

    return to_cents(base_amount - discount)
