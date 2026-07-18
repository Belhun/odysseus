"""SysForge (Business Management) plugin uninstall pipeline."""

from __future__ import annotations

import shutil
from typing import Any

from src.plugins.registry import (
    is_plugin_installed,
    plugin_data_dir,
    remove_installed_record,
    set_feature_flag,
)


def run_uninstall(*, remove_data: bool = False) -> dict[str, Any]:
    if not is_plugin_installed("sysforge"):
        return {
            "ok": True,
            "plugin_id": "sysforge",
            "already_uninstalled": True,
            "steps": [{"step": "marker", "status": "ok", "message": "Already uninstalled"}],
            "reload_required": False,
        }

    steps: list[dict[str, str]] = []

    set_feature_flag("sysforge", False)
    steps.append({"step": "feature", "status": "ok", "message": "Business Management feature disabled"})

    remove_installed_record("sysforge")
    steps.append({"step": "marker", "status": "ok", "message": "Install marker removed"})

    if remove_data:
        data_dir = plugin_data_dir("sysforge")
        if data_dir.is_dir():
            shutil.rmtree(data_dir)
        steps.append({"step": "data", "status": "ok", "message": "Plugin data removed"})
    else:
        steps.append({"step": "data", "status": "ok", "message": "Plugin data kept on disk"})

    return {
        "ok": True,
        "plugin_id": "sysforge",
        "steps": steps,
        "reload_required": False,
    }
