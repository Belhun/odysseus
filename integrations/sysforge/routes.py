"""SysForge Business Management API — gated by plugin install state."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from src.plugins.registry import is_plugin_active, read_installed_record


def _require_sysforge_plugin(_request: Request) -> None:
    if not is_plugin_active("sysforge"):
        raise HTTPException(404, "Business Management plugin is not installed")


def setup_sysforge_routes() -> APIRouter:
    router = APIRouter(
        prefix="/api/sysforge",
        tags=["sysforge"],
        dependencies=[Depends(_require_sysforge_plugin)],
    )

    @router.get("/status")
    def status():
        installed = read_installed_record("sysforge") or {}
        return {
            "ok": True,
            "plugin_id": "sysforge",
            "installed": True,
            "version": installed.get("version"),
            "installed_at": installed.get("installed_at"),
        }

    return router
