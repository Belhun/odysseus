"""Finance plugin uninstall pipeline."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from integrations.finance.database import reset_engine_cache
from src.plugins.registry import (
    plugin_data_dir,
    remove_installed_record,
    set_feature_flag,
)


def run_uninstall(*, remove_data: bool = False) -> dict[str, Any]:
    steps: list[dict[str, str]] = []

    reset_engine_cache()
    set_feature_flag("finance", False)
    steps.append({"step": "feature", "status": "ok", "message": "Finance feature disabled"})

    remove_installed_record("finance")
    steps.append({"step": "marker", "status": "ok", "message": "Install marker removed"})

    if remove_data:
        data_dir = plugin_data_dir("finance")
        if data_dir.is_dir():
            shutil.rmtree(data_dir)
        steps.append({"step": "data", "status": "ok", "message": "Plugin data removed"})
    else:
        steps.append({"step": "data", "status": "ok", "message": "Plugin data kept on disk"})

    return {
        "ok": True,
        "plugin_id": "finance",
        "steps": steps,
        "reload_required": True,
    }
