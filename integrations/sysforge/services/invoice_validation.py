"""Invoice header + item validation (desktop InvoiceValidationHelpers parity).

Empty item lists are allowed at the service layer so edit saves can clear lines
without losing the invoice header. Create / save-as-new enforce ≥1 line at the
API (or via ``require_items``).
"""

from __future__ import annotations

from typing import Any

from integrations.sysforge.db.money import from_basis_points, from_cents


class InvoiceValidationError(ValueError):
    """Invalid invoice or line-item payload."""


_VALID_STATUS = frozenset({"Estimate", "Invoiced", "Paid"})
_VALID_ITEM_TYPES = frozenset({"Part", "Labor", "Misc"})
_VALID_DISCOUNTS = frozenset({"None", "Percent", "Amount"})


def _get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


def validate_invoice(invoice: dict[str, Any]) -> None:
    """Validate header fields before save. Money is integer cents / bps."""
    if invoice is None:
        raise InvoiceValidationError("Invoice is required")

    client_id = _get(invoice, "client_id", "ClientId")
    if client_id is not None:
        try:
            cid = int(client_id)
        except (TypeError, ValueError) as exc:
            raise InvoiceValidationError("ClientId must be a positive id when set") from exc
        if cid <= 0:
            raise InvoiceValidationError("ClientId must be a positive id when set")

    for key, label in (
        ("parts_subtotal_cents", "PartsSubtotalCents"),
        ("labor_cost_cents", "LaborCostCents"),
        ("tax_amount_cents", "TaxAmountCents"),
        ("shipping_cost_cents", "ShippingCostCents"),
        ("final_total_cents", "FinalTotalCents"),
        ("shipping_rate_cents", "ShippingRateCents"),
    ):
        raw = _get(invoice, key, label, default=0)
        try:
            value = int(raw or 0)
        except (TypeError, ValueError) as exc:
            raise InvoiceValidationError(f"{label} must be an integer") from exc
        if value < 0:
            raise InvoiceValidationError(f"{label} must be non-negative")

    tax_bps = _get(invoice, "tax_rate_bps", "TaxRateBasisPoints", default=0)
    try:
        tax_bps_i = int(tax_bps or 0)
    except (TypeError, ValueError) as exc:
        raise InvoiceValidationError("Tax rate must be between 0 and 100.") from exc
    # 0–100% → 0–10000 bps
    if tax_bps_i < 0 or tax_bps_i > 10000:
        raise InvoiceValidationError("Tax rate must be between 0 and 100.")

    status = _get(invoice, "status", "Status", default="Estimate")
    if status is not None and str(status) not in _VALID_STATUS:
        raise InvoiceValidationError(
            f"Status must be one of: {', '.join(sorted(_VALID_STATUS))}"
        )


def validate_invoice_items(items: list[dict[str, Any]] | None) -> None:
    """Validate line items. Empty list is allowed (edit empty-header policy)."""
    if items is None:
        raise InvoiceValidationError("Items list is required")

    for i, item in enumerate(items):
        if item is None:
            raise InvoiceValidationError(f"items[{i}] is required")
        prefix = f"items[{i}]"

        part_name = _get(item, "part_name", "PartName", default="")
        if part_name is None or not str(part_name).strip():
            raise InvoiceValidationError(f"{prefix}.PartName is required")

        qty = _get(item, "quantity_milliunits", "QuantityMilliunits", default=1000)
        try:
            qty_i = int(qty)
        except (TypeError, ValueError) as exc:
            raise InvoiceValidationError(f"{prefix}.Quantity must be positive") from exc
        if qty_i <= 0:
            raise InvoiceValidationError(f"{prefix}.Quantity must be positive")

        for key, label in (
            ("unit_price_cents", "UnitPriceCents"),
            ("line_total_cents", "LineTotalCents"),
        ):
            raw = _get(item, key, label, default=0)
            try:
                value = int(raw or 0)
            except (TypeError, ValueError) as exc:
                raise InvoiceValidationError(f"{prefix}.{label} must be an integer") from exc
            if value < 0:
                raise InvoiceValidationError(f"{prefix}.{label} must be non-negative")

        discount_type = str(
            _get(item, "discount_type", "DiscountType", default="None") or "None"
        )
        if discount_type not in _VALID_DISCOUNTS:
            raise InvoiceValidationError(
                f"{prefix}.DiscountType must be one of: {', '.join(sorted(_VALID_DISCOUNTS))}"
            )

        discount_value = int(
            _get(item, "discount_value", "DiscountValue", default=0) or 0
        )
        if discount_type == "Percent":
            percent = from_basis_points(discount_value)
            if percent < 0 or percent > 100:
                raise InvoiceValidationError(
                    f"{prefix}.DiscountValue must be between 0 and 100 for percentage discounts."
                )
        elif discount_type == "Amount":
            if from_cents(discount_value) < 0:
                raise InvoiceValidationError(
                    f"{prefix}.DiscountValue must be non-negative"
                )

        item_type = str(_get(item, "item_type", "ItemType", default="Part") or "Part")
        if item_type not in _VALID_ITEM_TYPES:
            raise InvoiceValidationError(
                f"{prefix}.ItemType must be one of: {', '.join(sorted(_VALID_ITEM_TYPES))}"
            )
