"""Shared create-from-invoice orchestration (all UI entry points)."""

from __future__ import annotations

from typing import Any

from integrations.sysforge.services import invoice_devices
from integrations.sysforge.services import projects as project_service
from integrations.sysforge.services import work_orders
from integrations.sysforge.services.invoices import InvoiceNotFoundError, get_invoice


class CreateFromInvoiceError(ValueError):
    """Guards: no WO, no devices, all linked, blank device id."""

    def __init__(self, message: str, *, code: str = "create_from_invoice"):
        super().__init__(message)
        self.code = code


def create_from_invoice(
    *,
    invoice_id: int,
    invoice_device_id: int,
    device_id: str | None,
    category: str,
    invoice_item_ids: list[int] | None = None,
) -> dict[str, Any]:
    """
    Single create path used by header, Classic preview, and calculator.

    Rules:
    - Invoice must exist and have a linked work order.
    - Device must belong to invoice and have no project yet.
    - Whitespace-only device_id → refused (omit field entirely to auto-generate).
    """
    inv = get_invoice(invoice_id)
    if inv is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")

    wo_id = work_orders.get_work_order_id_for_invoice(invoice_id)
    if wo_id is None:
        raise CreateFromInvoiceError(
            "Accept estimate first",
            code="accept_first",
        )

    devices = invoice_devices.list_devices(invoice_id)
    if not devices:
        raise CreateFromInvoiceError(
            "Add a device on the estimate before creating a project",
            code="no_devices",
        )

    eligible = [d for d in devices if not d["has_project"]]
    if not eligible:
        raise CreateFromInvoiceError(
            "Every device on this invoice already has a project",
            code="all_have_projects",
        )

    target = next((d for d in devices if d["id"] == invoice_device_id), None)
    if target is None:
        raise CreateFromInvoiceError(
            "Invoice device does not belong to this invoice",
            code="device_mismatch",
        )
    if target["has_project"]:
        raise CreateFromInvoiceError(
            "A project already exists for this device.",
            code="device_has_project",
        )

    # Explicit blank/whitespace refused; None omitted → service generates.
    if device_id is not None and not str(device_id).strip():
        raise CreateFromInvoiceError("Device ID is required", code="blank_device_id")

    return project_service.create_project(
        wo_id,
        invoice_device_id,
        invoice_item_ids,
        device_id,
        category,
        refuse_blank_device_id=True,
    )


def eligible_devices(invoice_id: int) -> dict[str, Any]:
    """Preflight for wizard: WO check + devices without projects."""
    wo_id = work_orders.get_work_order_id_for_invoice(invoice_id)
    devices = invoice_devices.list_devices(invoice_id)
    eligible = [d for d in devices if not d["has_project"]]
    return {
        "work_order_id": wo_id,
        "devices": devices,
        "eligible": eligible,
        "can_create": wo_id is not None and len(eligible) > 0,
        "accept_first": wo_id is None,
        "no_devices": len(devices) == 0,
        "all_have_projects": len(devices) > 0 and len(eligible) == 0,
    }
