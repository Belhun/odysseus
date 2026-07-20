"""Phase 1 manage_sysforge integration tests."""

import json

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes
from src.tools.sysforge import do_manage_sysforge


@pytest.fixture()
def sysforge_tool_env(monkeypatch, tmp_path):
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    run_install()
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: True)

    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    transport = ASGITransport(app=app)

    import src.tools.sysforge as sf

    async def _sf_request_test(method, path, owner, **kwargs):
        if not path.startswith("/"):
            path = "/" + path
        headers = sf._internal_headers(owner=owner) if hasattr(sf, "_internal_headers") else {}
        from src.tools._common import _internal_headers

        headers = _internal_headers(owner=owner)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.request(
                method.upper(),
                path,
                params=kwargs.get("params"),
                json=kwargs.get("json_body") if kwargs.get("files") is None else None,
                files=kwargs.get("files"),
                data=kwargs.get("data"),
                headers=headers,
            )
        if resp.status_code == 204:
            return resp.status_code, {}
        try:
            body = resp.json()
        except Exception:
            body = {"detail": (resp.text or "")[:2000]}
        return resp.status_code, body

    monkeypatch.setattr("src.tools.sysforge._sf_request", _sf_request_test)

    from integrations.sysforge.services import clients as client_service

    created = client_service.add_client(
        {"first_name": "Test", "last_name": "Client", "phone_number": "555-0100"},
    )
    from integrations.sysforge.services.clients import rebuild_clients_fts

    rebuild_clients_fts()
    cid = created["id"]
    yield {"owner": "alice", "client_id": cid}


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_client_search_and_create(sysforge_tool_env):
    owner = sysforge_tool_env["owner"]
    cid = sysforge_tool_env["client_id"]
    result = await do_manage_sysforge(
        json.dumps({"action": "client_search", "q": "Test"}),
        owner=owner,
    )
    assert result["exit_code"] == 0
    assert str(cid) in result["response"] or "Client" in result["response"]


@pytest.mark.asyncio
@pytest.mark.area_routes
async def test_outstanding_list_empty(sysforge_tool_env):
    result = await do_manage_sysforge(
        json.dumps({"action": "outstanding_list"}),
        owner=sysforge_tool_env["owner"],
    )
    assert result["exit_code"] == 0
    assert "outstanding" in result["response"].lower()
