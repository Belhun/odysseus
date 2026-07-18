"""Optional plugin install / status / uninstall APIs."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.middleware import require_admin
from src.plugins import registry

logger = logging.getLogger(__name__)

_INSTALLERS = {
    "sysforge": "integrations.sysforge.install.run_install",
}
_UNINSTALLERS = {
    "sysforge": "integrations.sysforge.uninstall.run_uninstall",
}


class UninstallBody(BaseModel):
    remove_data: bool = False


def _run_callable(dotted: str, **kwargs: Any) -> dict[str, Any]:
    module_path, func_name = dotted.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    func = getattr(mod, func_name)
    return func(**kwargs) if kwargs else func()


def setup_plugin_routes() -> APIRouter:
    router = APIRouter(prefix="/api/plugins", tags=["plugins"])

    @router.get("/catalog")
    def plugin_catalog(request: Request):
        return {"plugins": registry.list_catalog()}

    @router.get("/{plugin_id}/status")
    def plugin_status(request: Request, plugin_id: str):
        try:
            return registry.plugin_status(plugin_id)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/{plugin_id}/install")
    def plugin_install(request: Request, plugin_id: str):
        require_admin(request)
        installer = _INSTALLERS.get(plugin_id)
        if not installer:
            raise HTTPException(404, f"Unknown plugin: {plugin_id}")
        try:
            return _run_callable(installer)
        except Exception as exc:
            logger.exception("plugin install failed: %s", plugin_id)
            raise HTTPException(500, "Install failed") from exc

    @router.post("/{plugin_id}/uninstall")
    def plugin_uninstall(request: Request, plugin_id: str, body: Optional[UninstallBody] = None):
        require_admin(request)
        body = body or UninstallBody()
        uninstaller = _UNINSTALLERS.get(plugin_id)
        if not uninstaller:
            raise HTTPException(404, f"Unknown plugin: {plugin_id}")
        try:
            return _run_callable(uninstaller, remove_data=body.remove_data)
        except Exception as exc:
            logger.exception("plugin uninstall failed: %s", plugin_id)
            raise HTTPException(500, "Uninstall failed") from exc

    return router
