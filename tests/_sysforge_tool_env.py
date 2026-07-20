"""Shared helpers for manage_sysforge integration tests."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from httpx import ASGITransport

from integrations.sysforge.install import run_install
from integrations.sysforge.routes import setup_sysforge_routes


def install_sysforge_plugin(monkeypatch, tmp_path) -> None:
    plugins_root = tmp_path / "plugins"
    monkeypatch.setattr("src.plugins.registry.PLUGINS_DATA_ROOT", plugins_root)
    monkeypatch.setattr("src.plugins.registry.plugin_data_dir", lambda pid: plugins_root / pid)
    monkeypatch.setattr("src.settings.FEATURES_FILE", str(tmp_path / "features.json"))
    run_install()
    monkeypatch.setattr("integrations.sysforge.routes.is_plugin_active", lambda _pid: True)


def patch_sysforge_loopback(monkeypatch) -> ASGITransport:
    app = FastAPI()
    app.include_router(setup_sysforge_routes())
    transport = ASGITransport(app=app)

    import src.tools.sysforge as sf
    from src.tools._common import _internal_headers

    async def _sf_request_test(method, path, owner, **kwargs):
        if not path.startswith("/"):
            path = "/" + path
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
    return transport
