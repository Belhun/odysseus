"""Ledger CRUD, pins, and posted-balance route tests."""

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient
from tests.conftest import make_finance_test_engine

import integrations.finance.database as finance_db
import integrations.finance.routes as finance_routes
from integrations.finance.models import FinanceBase, FinanceMutationLog
from integrations.finance.routes import setup_finance_routes
from tests.fixtures.finance.synthetic_samples import WELLS_FARGO_SAMPLE


@pytest.fixture()
def finance_client(monkeypatch, tmp_path):
    finance_db.reset_engine_cache()
    db_path = tmp_path / "finance.db"
    monkeypatch.setattr(finance_db, "finance_db_path", lambda: db_path)
    monkeypatch.setattr("integrations.finance.routes.is_plugin_active", lambda _pid: True)

    engine = make_finance_test_engine(db_path)
    FinanceBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(finance_routes, "get_session_factory", lambda: session_factory)

    def _fake_require_user(request):
        return "testuser"

    monkeypatch.setattr(finance_routes, "require_user", _fake_require_user)

    app = FastAPI()
    app.include_router(setup_finance_routes())
    with TestClient(app) as client:
        yield client
    finance_db.reset_engine_cache()


@pytest.mark.area_routes
def test_account_purpose_and_pins_round_trip(finance_client):
    res = finance_client.post("/api/finance/accounts", json={
        "name": "Trip checking",
        "account_type": "checking",
        "purpose": "trip",
        "opening_balance_cents": 50000,
        "posted_pin_cents": 48000,
        "posted_pin_as_of": "2026-08-01",
        "available_cents": 47000,
        "available_as_of": "2026-08-01",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["purpose"] == "trip"
    assert body["posted_cents"] == 50000
    assert body["balance_cents"] == 50000
    assert body["posted_pin_cents"] == 48000
    assert body["available_cents"] == 47000

    bad = finance_client.post("/api/finance/accounts", json={
        "name": "Nope",
        "purpose": "household",
    })
    assert bad.status_code == 400

    processor = finance_client.post("/api/finance/accounts", json={
        "name": "PayPal",
        "purpose": "processor",
        "rail": "paypal",
    })
    assert processor.status_code == 200
    assert processor.json()["rail"] == "paypal"


@pytest.mark.area_routes
def test_pins_endpoint_does_not_change_posted(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "WF",
        "opening_balance_cents": 10000,
    }).json()
    pinned = finance_client.post(
        f"/api/finance/accounts/{acct['id']}/pins",
        json={"posted_pin_cents": 999, "available_cents": 111},
    )
    assert pinned.status_code == 200
    assert pinned.json()["posted_pin_cents"] == 999
    assert pinned.json()["available_cents"] == 111
    assert pinned.json()["posted_cents"] == 10000


@pytest.mark.area_routes
def test_import_and_batch_delete_never_touch_pins(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "WF",
        "opening_balance_cents": 0,
        "posted_pin_cents": 77777,
        "available_cents": 88888,
    }).json()
    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    ).json()
    commit = finance_client.post("/api/finance/import/commit", json={"preview_id": preview["preview_id"]})
    assert commit.status_code == 200
    after_import = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert after_import["posted_pin_cents"] == 77777
    assert after_import["available_cents"] == 88888
    assert after_import["posted_cents"] != 77777

    batches = finance_client.get("/api/finance/import/batches").json()["batches"]
    finance_client.delete(f"/api/finance/import/batches/{batches[0]['id']}")
    after_delete = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert after_delete["posted_pin_cents"] == 77777
    assert after_delete["available_cents"] == 88888
    assert after_delete["posted_cents"] == 0


@pytest.mark.area_routes
def test_import_applies_opening_posted_from_statement_csv(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "WF",
        "opening_balance_cents": 0,
    }).json()
    csv_text = """# odysseus-finance: v1
# source: wells-statement-pdf
# opening_posted: 104.14
# opening_as_of: 2018-12-12
DATE,DESCRIPTION,AMOUNT,CHECK #
12/12/2018,Test Cafe,-25.00,
01/03/2019,Direct Deposit,50.00,
"""
    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("wells-from-statements.csv", csv_text.encode("utf-8"), "text/csv")},
    ).json()
    assert preview["opening"]["opening_posted_cents"] == 10414
    assert preview["opening"]["opening_as_of"] == "2018-12-12"
    commit = finance_client.post(
        "/api/finance/import/commit",
        json={"preview_id": preview["preview_id"], "apply_opening": True},
    )
    assert commit.status_code == 200
    assert commit.json()["opening_applied"] is True
    after = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert after["opening_balance_cents"] == 10414
    assert after["opening_balance_date"] == "2018-12-12"
    assert after["posted_cents"] == 10414 - 2500 + 5000


@pytest.mark.area_routes
def test_manual_create_void_delete_and_imported_409(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "Cash",
        "opening_balance_cents": 10000,
        "posted_pin_cents": 10000,
    }).json()
    created = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-08-02",
        "amount_cents": -1500,
        "payee": "Parking",
        "status": "cleared",
    })
    assert created.status_code == 200
    tx = created.json()
    assert tx["source"] == "manual"
    assert tx["is_manual"] is True

    listed = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert listed["posted_cents"] == 8500
    assert listed["posted_pin_cents"] == 10000

    voided = finance_client.post(f"/api/finance/transactions/{tx['id']}/void")
    assert voided.status_code == 200
    assert voided.json()["status"] == "void"
    after_void = finance_client.get("/api/finance/accounts").json()["accounts"][0]
    assert after_void["posted_cents"] == 10000
    assert after_void["posted_pin_cents"] == 10000

    hidden = finance_client.get("/api/finance/transactions", params={"account_id": acct["id"]})
    assert hidden.json()["total"] == 0
    shown = finance_client.get(
        "/api/finance/transactions",
        params={"account_id": acct["id"], "include_void": True},
    )
    assert shown.json()["total"] == 1

    finance_client.post(f"/api/finance/transactions/{tx['id']}/unvoid")
    deleted = finance_client.delete(f"/api/finance/transactions/{tx['id']}")
    assert deleted.status_code == 200

    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"]},
        files={"file": ("wells.csv", WELLS_FARGO_SAMPLE.encode("utf-8"), "text/csv")},
    ).json()
    finance_client.post("/api/finance/import/commit", json={"preview_id": preview["preview_id"]})
    imported = finance_client.get("/api/finance/transactions", params={"account_id": acct["id"]}).json()
    imported_id = imported["transactions"][0]["id"]
    blocked = finance_client.delete(f"/api/finance/transactions/{imported_id}")
    assert blocked.status_code == 409


@pytest.mark.area_routes
def test_patch_manual_amount_and_mutation_log(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={
        "name": "Cash",
        "opening_balance_cents": 0,
    }).json()
    tx = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-08-02",
        "amount_cents": -400,
        "payee": "Coffee",
    }).json()
    patched = finance_client.patch(
        f"/api/finance/transactions/{tx['id']}",
        json={"amount_cents": -500, "date": "2026-08-03"},
    )
    assert patched.status_code == 200
    assert patched.json()["amount_cents"] == -500
    assert patched.json()["date"] == "2026-08-03"
    assert finance_client.get("/api/finance/accounts").json()["accounts"][0]["posted_cents"] == -500

    from integrations.finance.routes import get_session_factory

    db = get_session_factory()()
    try:
        logs = db.query(FinanceMutationLog).filter(FinanceMutationLog.owner == "testuser").all()
        actions = {row.action for row in logs}
        assert "create" in actions
        assert "patch" in actions
    finally:
        db.close()


@pytest.mark.area_routes
def test_manual_row_then_matching_import_is_flagged_not_skipped(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "Cash", "account_type": "checking"}).json()
    finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"],
        "date": "2026-08-01",
        "amount_cents": -4000,
        "payee": "GROCERY",
    })
    csv_body = '"DATE","DESCRIPTION","AMOUNT","CHECK #","STATUS"\n"08/01/2026","GROCERY","-40.00","","Posted"\n'
    preview = finance_client.post(
        "/api/finance/import/preview",
        data={"account_id": acct["id"], "preset": "csv_wells_fargo"},
        files={"file": ("manual.csv", csv_body.encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200
    body = preview.json()
    statuses = {row["status"] for row in body["rows"]}
    assert "possible_manual_duplicate" in statuses
    assert body["new_count"] >= 1


@pytest.mark.area_routes
def test_invalid_month_returns_400(finance_client):
    res = finance_client.get("/api/finance/reports/cashflow", params={"month": "2026-13"})
    assert res.status_code == 400


@pytest.mark.area_routes
def test_account_fields_are_editable_and_pin_delta_renders(finance_client):
    created = finance_client.post("/api/finance/accounts", json={
        "name": "Navy Fed #2",
        "account_type": "checking",
        "opening_balance_cents": 10000,
    }).json()
    assert created["purpose"] == "operating"
    patched = finance_client.patch(f"/api/finance/accounts/{created['id']}", json={
        "purpose": "trip",
        "opening_balance_cents": 20000,
        "opening_balance_date": "2026-07-01",
        "posted_pin_cents": 23742,
        "posted_pin_as_of": "2026-08-12",
        "available_cents": 18000,
        "available_as_of": "2026-08-01",
    })
    assert patched.status_code == 200
    body = patched.json()
    assert body["purpose"] == "trip"
    assert body["opening_balance_cents"] == 20000
    assert body["posted_pin_cents"] == 23742
    assert body["posted_pin_delta_cents"] == 20000 - 23742
    assert body["available_cents"] == 18000
    listed = finance_client.get("/api/finance/accounts").json()["accounts"]
    row = next(a for a in listed if a["id"] == created["id"])
    assert row["posted_pin_delta_cents"] == -3742


@pytest.mark.area_routes
def test_bulk_classify_and_apply_to_payee(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "Wells"}).json()
    a = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"], "date": "2026-06-01", "amount_cents": -1500, "payee": "STARBUCKS",
    }).json()
    b = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"], "date": "2026-06-02", "amount_cents": -2200, "payee": "STARBUCKS",
    }).json()
    c = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"], "date": "2026-06-03", "amount_cents": -900, "payee": "COSTCO",
    }).json()
    res = finance_client.post("/api/finance/transactions/bulk", json={
        "transaction_ids": [a["id"]],
        "movement_class": "spend",
        "apply_to_payee": True,
    })
    assert res.status_code == 200
    assert res.json()["updated"] == 2
    txs = finance_client.get("/api/finance/transactions", params={"account_id": acct["id"]}).json()["transactions"]
    by_id = {tx["id"]: tx for tx in txs}
    assert by_id[a["id"]]["movement_class"] == "spend"
    assert by_id[b["id"]]["movement_class"] == "spend"
    assert by_id[c["id"]]["movement_class"] is None
    filtered = finance_client.get(
        "/api/finance/transactions",
        params={"account_id": acct["id"], "unclassified": True},
    ).json()["transactions"]
    assert {tx["id"] for tx in filtered} == {c["id"]}


@pytest.mark.area_routes
def test_transfers_category_sets_transfer_class(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "Wells"}).json()
    cats = finance_client.get("/api/finance/categories").json()["categories"]
    transfers = next(c for c in cats if c["name"].lower().startswith("transfers"))
    tx = finance_client.post("/api/finance/transactions", json={
        "account_id": acct["id"], "date": "2026-06-01", "amount_cents": -50000, "payee": "NAVY FEDERAL",
    }).json()
    patched = finance_client.patch(f"/api/finance/transactions/{tx['id']}", json={
        "category_id": transfers["id"],
    })
    assert patched.status_code == 200
    assert patched.json()["movement_class"] == "transfer"


STATEMENT_SETUP_CSV = """# odysseus-finance: v1
# source: wells-statement-pdf
# opening_posted: 100.00
# opening_as_of: 2026-06-01
DATE,DESCRIPTION,AMOUNT,CHECK #,DAILY_BALANCE,STATEMENT_START,STATEMENT_END,SOURCE_PDF
06/26/2026,Purchase authorized on 06/25 TEST MERCHANT PURCHASE Card 1111,-9.85,,90.15,2026-06-01,2026-06-30,jun.pdf
06/25/2026,PAYROLL DEPOSIT,1500.00,,1600.00,2026-06-01,2026-06-30,jun.pdf
"""


def _import_csv(client, account_id, name, text, apply_opening=False):
    preview = client.post(
        "/api/finance/import/preview",
        data={"account_id": account_id},
        files={"file": (name, text.encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    commit = client.post(
        "/api/finance/import/commit",
        json={
            "preview_id": body["preview_id"],
            "apply_opening": apply_opening,
        },
    )
    assert commit.status_code == 200, commit.text
    return body, commit.json()


@pytest.mark.area_routes
def test_statement_setup_enriches_thin_csv_without_duplicating(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF"}).json()
    first_preview, first_commit = _import_csv(
        finance_client, acct["id"], "wells.csv", WELLS_FARGO_SAMPLE
    )
    assert first_preview["new_count"] == 2
    assert first_commit["imported_count"] == 2

    second_preview, second_commit = _import_csv(
        finance_client, acct["id"], "wells-from-statements.csv", STATEMENT_SETUP_CSV
    )
    assert second_preview["new_count"] == 0
    assert second_preview["enrich_count"] == 2
    assert second_preview["duplicate_count"] == 0
    assert second_commit["imported_count"] == 0
    assert second_commit["enriched_count"] == 2

    listed = finance_client.get(
        "/api/finance/transactions", params={"account_id": acct["id"]}
    ).json()["transactions"]
    assert len(listed) == 2
    by_amount = {row["amount_cents"]: row for row in listed}
    merchant = by_amount[-985]
    assert merchant["daily_balance_cents"] == 9015
    assert merchant["statement_start"] == "2026-06-01"
    assert merchant["source_statement"] == "jun.pdf"
    assert "TEST MERCHANT PURCHASE" in merchant["payee"]
    assert merchant["payee"].startswith("Purchase authorized")

    third_preview, third_commit = _import_csv(
        finance_client, acct["id"], "wells-from-statements.csv", STATEMENT_SETUP_CSV
    )
    assert third_preview["new_count"] == 0
    assert third_preview["enrich_count"] == 0
    assert third_preview["duplicate_count"] == 2
    assert third_commit["imported_count"] == 0
    assert third_commit["enriched_count"] == 0
    listed_again = finance_client.get(
        "/api/finance/transactions", params={"account_id": acct["id"]}
    ).json()["transactions"]
    assert len(listed_again) == 2
    assert by_amount[-985]["daily_balance_cents"] == 9015


@pytest.mark.area_routes
def test_import_commit_releases_savepoints_for_large_files(finance_client):
    """Stacked begin_nested() savepoints recurse on commit past ~1000 rows."""
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF"}).json()
    lines = ["DATE,DESCRIPTION,AMOUNT"]
    for i in range(1200):
        lines.append(f"01/01/2024,Payee {i},-1.00")
    preview, commit = _import_csv(
        finance_client, acct["id"], "bulk.csv", "\n".join(lines) + "\n"
    )
    assert preview["new_count"] == 1200
    assert commit["imported_count"] == 1200
    listed = finance_client.get(
        "/api/finance/transactions",
        params={"account_id": acct["id"], "limit": 1},
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 1200


@pytest.mark.area_routes
def test_same_day_same_amount_different_payees_do_not_merge(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF"}).json()
    thin = """DATE,DESCRIPTION,AMOUNT
01/05/2024,Starbucks,-4.50
01/05/2024,Uber,-4.50
"""
    _import_csv(finance_client, acct["id"], "thin.csv", thin)
    setup = """DATE,DESCRIPTION,AMOUNT,DAILY_BALANCE,STATEMENT_START,STATEMENT_END,SOURCE_PDF
01/05/2024,Starbucks,-4.50,20.00,2024-01-01,2024-01-31,jan.pdf
01/05/2024,Uber,-4.50,15.50,2024-01-01,2024-01-31,jan.pdf
"""
    preview, commit = _import_csv(finance_client, acct["id"], "setup.csv", setup)
    assert preview["new_count"] == 0
    assert preview["enrich_count"] == 2
    assert commit["imported_count"] == 0
    listed = finance_client.get(
        "/api/finance/transactions", params={"account_id": acct["id"]}
    ).json()["transactions"]
    assert len(listed) == 2
    by_payee = {row["payee"]: row for row in listed}
    assert by_payee["Starbucks"]["daily_balance_cents"] == 2000
    assert by_payee["Uber"]["daily_balance_cents"] == 1550


@pytest.mark.area_routes
def test_statement_reimport_adds_only_new_rows(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF"}).json()
    _import_csv(finance_client, acct["id"], "wells.csv", WELLS_FARGO_SAMPLE)
    setup = (
        STATEMENT_SETUP_CSV.rstrip()
        + "\n06/27/2026,New Cafe,-3.00,,87.15,2026-06-01,2026-06-30,jun.pdf\n"
    )
    preview, commit = _import_csv(
        finance_client, acct["id"], "wells-from-statements.csv", setup
    )
    assert preview["new_count"] == 1
    assert preview["enrich_count"] == 2
    assert commit["imported_count"] == 1
    listed = finance_client.get(
        "/api/finance/transactions", params={"account_id": acct["id"]}
    ).json()["transactions"]
    assert len(listed) == 3
    cafe = next(row for row in listed if row["payee"] == "New Cafe")
    assert cafe["daily_balance_cents"] == 8715


@pytest.mark.area_routes
def test_enrich_does_not_overwrite_existing_values(finance_client):
    acct = finance_client.post("/api/finance/accounts", json={"name": "WF"}).json()
    _import_csv(finance_client, acct["id"], "wells.csv", WELLS_FARGO_SAMPLE)
    _import_csv(
        finance_client, acct["id"], "wells-from-statements.csv", STATEMENT_SETUP_CSV
    )
    thinner = """DATE,DESCRIPTION,AMOUNT,DAILY_BALANCE
06/26/2026,TEST MERCHANT PURCHASE,-9.85,1.00
"""
    preview, commit = _import_csv(finance_client, acct["id"], "later.csv", thinner)
    assert preview["new_count"] == 0
    assert commit["imported_count"] == 0
    listed = finance_client.get(
        "/api/finance/transactions", params={"account_id": acct["id"]}
    ).json()["transactions"]
    merchant = next(row for row in listed if row["amount_cents"] == -985)
    assert merchant["daily_balance_cents"] == 9015
    assert merchant["payee"].startswith("Purchase authorized")
