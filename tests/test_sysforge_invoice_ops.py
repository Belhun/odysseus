"""Invoice ops: PDF generate/download, email via host, payments schema."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db.migration_runner import ensure_schema
from integrations.sysforge.install import run_install
from integrations.sysforge.pdf_invoice import generate_invoice_pdf
from integrations.sysforge.routes import setup_sysforge_routes
from integrations.sysforge.services import invoice_documents
from integrations.sysforge.services import invoice_email
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services import payments as payments_service
from integrations.sysforge.services.invoice_email import InvoiceEmailError
from integrations.sysforge.services.invoices import InvoiceNotFoundError


def _install_active(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr(
        "src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid
    )
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    result = run_install()
    assert result["ok"] is True
    monkeypatch.setattr(
        "integrations.sysforge.routes.is_plugin_active", lambda _pid: True
    )
    ensure_schema()
    return plugins_root


def _client(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    return TestClient(app)


def _item(*, part_name="Screen", unit_price_cents=5000, quantity_milliunits=1000):
    return {
        "part_id": None,
        "part_name": part_name,
        "sku": None,
        "quantity_milliunits": quantity_milliunits,
        "unit_price_cents": unit_price_cents,
        "discount_type": "None",
        "discount_value": 0,
        "is_taxable": True,
        "sort_order": 0,
        "item_type": "Part",
        "supplier_id": None,
    }


def _make_invoice(**kwargs):
    payload = {
        "name": "Alex - Phone Repair",
        "client_info": "Alex Rivera",
        "tax_rate_bps": 725,
        "include_tax": True,
        "include_shipping": False,
    }
    payload.update(kwargs)
    items = payload.pop("items", None) or [_item()]
    return invoice_service.create_invoice(payload, items)


@pytest.mark.area_routes
def test_pdf_bytes_magic_and_content(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv = _make_invoice()
    pdf, loaded = generate_invoice_pdf(inv["id"])
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 100
    assert loaded["final_total_cents"] == 5363

    from integrations.sysforge.pdf_invoice import _layout_lines

    lines = "\n".join(_layout_lines(loaded))
    assert "Alex" in lines
    assert f"TotalCents: {loaded['final_total_cents']}" in lines

    try:
        import fitz

        doc = fitz.open(stream=pdf, filetype="pdf")
        text = "".join(page.get_text() for page in doc)
        doc.close()
        assert "Alex" in text
        assert f"TotalCents: {loaded['final_total_cents']}" in text
    except ImportError:
        assert b"Alex" in pdf
        assert f"TotalCents: {loaded['final_total_cents']}".encode() in pdf


@pytest.mark.area_routes
def test_pdf_download_endpoint(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = _make_invoice()
    res = client.get(f"/api/sysforge/invoices/{inv['id']}/pdf")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("application/pdf")
    assert res.content.startswith(b"%PDF")
    assert "attachment" in res.headers.get("content-disposition", "")

    conn = db_connection.connect()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM InvoiceDocuments WHERE InvoiceId = ?",
            (inv["id"],),
        ).fetchone()["c"]
        assert count >= 1
    finally:
        conn.close()


@pytest.mark.area_routes
def test_pdf_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    res = client.get("/api/sysforge/invoices/99999/pdf")
    assert res.status_code == 404


@pytest.mark.area_routes
def test_email_happy_path_sets_sent_at(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv = _make_invoice()
    captured = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "message_id": "<test@odysseus.local>"}

    # Bypass staging/host by injecting send_fn after staging — wrap send_invoice_email
    monkeypatch.setattr(
        invoice_email,
        "_stage_compose_upload",
        lambda pdf, name: "token_invoice.pdf",
    )

    result = invoice_email.send_invoice_email(
        inv["id"],
        to="alex@example.com",
        subject="Test invoice",
        owner="tester",
        send_fn=fake_send,
    )
    assert result["ok"] is True
    assert result["sent_at"]
    assert result["to"] == "alex@example.com"
    assert captured["to"] == "alex@example.com"
    assert captured["attachment_token"] == "token_invoice.pdf"

    reloaded = invoice_service.get_invoice(inv["id"])
    assert reloaded["sent_at"] is not None
    assert reloaded["status"] == "Invoiced"  # Estimate → Invoiced on send


@pytest.mark.area_routes
def test_email_failure_no_sent_at(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv = _make_invoice()
    monkeypatch.setattr(
        invoice_email,
        "_stage_compose_upload",
        lambda pdf, name: "token_invoice.pdf",
    )

    def fail_send(**_kwargs):
        raise InvoiceEmailError("SMTP unavailable")

    with pytest.raises(InvoiceEmailError):
        invoice_email.send_invoice_email(
            inv["id"],
            to="alex@example.com",
            send_fn=fail_send,
        )
    reloaded = invoice_service.get_invoice(inv["id"])
    assert reloaded["sent_at"] is None
    assert reloaded["status"] == "Estimate"


@pytest.mark.area_routes
def test_email_endpoint_requires_to(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = _make_invoice()  # no client email
    monkeypatch.setattr(
        invoice_email,
        "_stage_compose_upload",
        lambda pdf, name: "token.pdf",
    )
    res = client.post(
        f"/api/sysforge/invoices/{inv['id']}/email",
        json={},
    )
    assert res.status_code == 400
    assert "recipient" in res.json()["detail"].lower() or "to" in res.json()["detail"].lower()


@pytest.mark.area_routes
def test_email_endpoint_502_on_host_failure(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = _make_invoice()
    monkeypatch.setattr(
        invoice_email,
        "_stage_compose_upload",
        lambda pdf, name: "token.pdf",
    )

    def fail_send(**_kwargs):
        raise InvoiceEmailError("No SMTP-capable email account configured")

    monkeypatch.setattr(invoice_email, "_send_via_host", fail_send)
    res = client.post(
        f"/api/sysforge/invoices/{inv['id']}/email",
        json={"to": "alex@example.com"},
    )
    assert res.status_code == 502
    reloaded = invoice_service.get_invoice(inv["id"])
    assert reloaded["sent_at"] is None


@pytest.mark.area_routes
def test_payment_partial_and_void(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    inv = _make_invoice(include_tax=False, tax_rate_bps=0)  # total 5000
    assert inv["final_total_cents"] == 5000

    first = payments_service.add_payment(
        inv["id"], amount_cents=2000, method="Cash"
    )
    assert first["balance_cents"] == 3000
    assert first["status"] != "Paid"

    second = payments_service.add_payment(
        inv["id"], amount_cents=3000, method="Card"
    )
    assert second["balance_cents"] == 0
    assert second["status"] == "Paid"

    voided = payments_service.void_payment(
        first["payment"]["id"], reason="Wrong amount"
    )
    assert voided["payment"]["is_voided"] is True
    assert voided["balance_cents"] == 2000
    assert voided["status"] == "Invoiced"

    outstanding = payments_service.list_outstanding()
    assert any(r["invoice_id"] == inv["id"] for r in outstanding)


@pytest.mark.area_routes
def test_payments_api(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)
    inv = _make_invoice(include_tax=False, tax_rate_bps=0)
    res = client.post(
        f"/api/sysforge/invoices/{inv['id']}/payments",
        json={"amount_cents": 1000, "method": "Check", "reference": "1001"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["balance_cents"] == 4000

    listed = client.get(f"/api/sysforge/invoices/{inv['id']}/payments")
    assert listed.status_code == 200
    assert len(listed.json()["payments"]) == 1

    out = client.get("/api/sysforge/invoices/outstanding")
    assert out.status_code == 200
    assert any(r["invoice_id"] == inv["id"] for r in out.json()["invoices"])


@pytest.mark.area_routes
def test_generate_and_persist_writes_file(monkeypatch, tmp_path):
    plugins = _install_active(monkeypatch, tmp_path)
    inv = _make_invoice()
    pdf, _invoice, doc = invoice_documents.generate_and_persist(inv["id"])
    assert pdf.startswith(b"%PDF")
    assert doc["sha256"]
    path = plugins / "sysforge" / "documents" / doc["stored_rel_path"]
    assert path.is_file()
    assert path.read_bytes() == pdf


@pytest.mark.area_routes
def test_sales_report_json_and_csv(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    client = _client(monkeypatch, tmp_path)
    inv = _make_invoice(include_tax=True, tax_rate_bps=725)
    payments_service.add_payment(inv["id"], amount_cents=1000, method="Cash")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    res = client.get(
        "/api/sysforge/reports/sales",
        params={"from": today, "to": today},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["summary"]["invoice_count"] == 1
    assert body["summary"]["tax_amount_cents"] == inv["tax_amount_cents"]
    assert body["summary"]["collected_payments_cents"] == 1000
    assert body["summary"]["outstanding_cents"] == inv["final_total_cents"] - 1000
    assert len(body["invoices"]) == 1
    assert body["invoices"][0]["invoice_id"] == inv["id"]

    csv_res = client.get(
        "/api/sysforge/reports/sales",
        params={"from": today, "to": today, "format": "csv"},
    )
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers.get("content-type", "")
    text = csv_res.text
    assert "metric,value_cents_or_count" in text
    assert "invoice_count,1" in text
    assert "tax_amount_cents," in text
    assert str(inv["id"]) in text

    empty = client.get(
        "/api/sysforge/reports/sales",
        params={"from": "2000-01-01", "to": "2000-01-02"},
    )
    assert empty.status_code == 200
    assert empty.json()["summary"]["invoice_count"] == 0

    bad = client.get(
        "/api/sysforge/reports/sales",
        params={"from": "2026-07-10", "to": "2026-07-01"},
    )
    assert bad.status_code == 400


@pytest.mark.area_routes
def test_pdf_unknown_raises(monkeypatch, tmp_path):
    _install_active(monkeypatch, tmp_path)
    with pytest.raises(InvoiceNotFoundError):
        generate_invoice_pdf(99999)
