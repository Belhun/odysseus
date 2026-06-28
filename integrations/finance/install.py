"""Finance plugin install pipeline."""

from __future__ import annotations

from typing import Any

from integrations.finance.database import init_finance_db, write_default_config
from src.plugins.registry import (
    is_plugin_active,
    is_plugin_installed,
    load_manifest,
    plugin_data_dir,
    read_installed_record,
    set_feature_flag,
    write_installed_record,
)


def run_install() -> dict[str, Any]:
    manifest = load_manifest("finance")
    version = manifest.get("version", "0.1.0")

    if is_plugin_installed("finance"):
        if not is_plugin_active("finance"):
            set_feature_flag("finance", True)
        installed = read_installed_record("finance") or {}
        return {
            "ok": True,
            "plugin_id": "finance",
            "version": installed.get("version", version),
            "already_installed": True,
            "steps": [{"step": "marker", "status": "ok", "message": "Already installed"}],
            "reload_required": False,
        }

    steps: list[dict[str, str]] = []

    data_dir = plugin_data_dir("finance")
    data_dir.mkdir(parents=True, exist_ok=True)
    steps.append({"step": "prepare", "status": "ok", "message": "Plugin data directory ready"})

    init_finance_db()
    steps.append({"step": "database", "status": "ok", "message": "Finance database initialized"})

    write_default_config()
    steps.append({"step": "config", "status": "ok", "message": "Default config written"})

    write_installed_record("finance", version)
    steps.append({"step": "marker", "status": "ok", "message": "Install marker written"})

    set_feature_flag("finance", True)
    steps.append({"step": "feature", "status": "ok", "message": "Finance feature enabled"})

    return {
        "ok": True,
        "plugin_id": "finance",
        "version": version,
        "steps": steps,
        "reload_required": False,
    }
