"""Finance plugin install pipeline."""

from __future__ import annotations

from typing import Any

from integrations.finance.database import init_finance_db, write_default_config
from src.plugins.registry import (
    load_manifest,
    plugin_data_dir,
    set_feature_flag,
    write_installed_record,
)


def run_install() -> dict[str, Any]:
    manifest = load_manifest("finance")
    version = manifest.get("version", "0.1.0")
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
        "reload_required": True,
    }
