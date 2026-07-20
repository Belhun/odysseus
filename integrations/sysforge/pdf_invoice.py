"""Generate invoice PDF bytes (shop letterhead v1).

Prefers PyMuPDF when installed; falls back to a minimal PDF writer so
core Business paths stay MIT-clean without the optional AGPL dep.
"""

from __future__ import annotations

from typing import Any

from integrations.sysforge.config import load_config
from integrations.sysforge.db.money import from_basis_points, from_cents, from_milliunits
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services.invoices import InvoiceNotFoundError


def _money_str(cents: int) -> str:
    return f"${from_cents(int(cents or 0)):,.2f}"


def _qty_str(milli: int) -> str:
    q = from_milliunits(int(milli or 0))
    if q == q.to_integral_value():
        return str(int(q))
    return f"{q:.3f}".rstrip("0").rstrip(".")


def _shop_name() -> str:
    cfg = load_config()
    name = cfg.get("shop_name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return "Business"


def _layout_lines(invoice: dict[str, Any]) -> list[str]:
    """Build plain-text lines for the PDF body (also used by tests)."""
    client = invoice.get("client") or {}
    client_name = (
        client.get("display_name")
        or invoice.get("client_info")
        or "No client"
    )
    inv_label = (
        invoice.get("display_label")
        or invoice.get("name")
        or f"#{invoice.get('id')}"
    )
    lines: list[str] = [
        _shop_name(),
        "",
        f"Invoice: {inv_label}",
        f"Status: {invoice.get('status') or 'Estimate'}",
        f"Client: {client_name}",
    ]
    if client.get("email"):
        lines.append(f"Email: {client['email']}")
    if client.get("phone_number"):
        lines.append(f"Phone: {client['phone_number']}")
    if invoice.get("date_created"):
        lines.append(f"Created: {invoice['date_created']}")
    lines.append("")
    lines.append("Item                          Qty      Unit        Line")
    lines.append("-" * 60)
    for item in invoice.get("items") or []:
        name = str(item.get("part_name") or "")[:28].ljust(28)
        qty = _qty_str(int(item.get("quantity_milliunits") or 0)).rjust(6)
        unit = _money_str(int(item.get("unit_price_cents") or 0)).rjust(10)
        line = _money_str(int(item.get("line_total_cents") or 0)).rjust(10)
        lines.append(f"{name} {qty} {unit} {line}")
    lines.append("-" * 60)
    lines.append(f"Parts:     {_money_str(int(invoice.get('parts_subtotal_cents') or 0))}")
    lines.append(f"Labor:     {_money_str(int(invoice.get('labor_cost_cents') or 0))}")
    tax_bps = int(invoice.get("tax_rate_bps") or 0)
    tax_label = f"Tax ({from_basis_points(tax_bps)}%):"
    lines.append(f"{tax_label:<11}{_money_str(int(invoice.get('tax_amount_cents') or 0))}")
    lines.append(f"Shipping:  {_money_str(int(invoice.get('shipping_cost_cents') or 0))}")
    total_cents = int(invoice.get("final_total_cents") or 0)
    lines.append(f"TOTAL:     {_money_str(total_cents)}")
    # Embed raw cents for golden tests (no float drift).
    lines.append(f"TotalCents: {total_cents}")
    return lines


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _generate_minimal_pdf(lines: list[str]) -> bytes:
    """Single-page PDF with Helvetica text; no third-party deps."""
    y = 750
    content_parts = ["BT", "/F1 11 Tf", "14 TL", f"1 0 0 1 50 {y} Tm"]
    first = True
    for line in lines:
        esc = _pdf_escape(line)
        if first:
            content_parts.append(f"({esc}) Tj")
            first = False
        else:
            content_parts.append("T*")
            content_parts.append(f"({esc}) Tj")
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("latin-1", errors="replace")

    objects: list[bytes] = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
    )
    objects.append(
        f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii")
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


def _generate_with_fitz(lines: list[str]) -> bytes:
    import fitz  # PyMuPDF — optional

    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        y = 72
        for line in lines:
            page.insert_text((50, y), line, fontsize=10, fontname="helv")
            y += 14
            if y > 740:
                page = doc.new_page(width=612, height=792)
                y = 72
        return doc.tobytes()
    finally:
        doc.close()


def render_invoice_pdf_bytes(invoice: dict[str, Any]) -> bytes:
    """Render PDF for an already-loaded invoice dict."""
    lines = _layout_lines(invoice)
    try:
        return _generate_with_fitz(lines)
    except ImportError:
        return _generate_minimal_pdf(lines)


def generate_invoice_pdf(invoice_id: int) -> tuple[bytes, dict[str, Any]]:
    """Load invoice and return (pdf_bytes, invoice_dict). Raises InvoiceNotFoundError."""
    invoice = invoice_service.get_invoice(invoice_id)
    if invoice is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    return render_invoice_pdf_bytes(invoice), invoice


def suggested_pdf_filename(invoice: dict[str, Any]) -> str:
    label = invoice.get("name") or invoice.get("display_label") or f"invoice-{invoice.get('id')}"
    safe = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in str(label))
    safe = "-".join(safe.split())[:80] or f"invoice-{invoice.get('id')}"
    return f"{safe}.pdf"
