"""SysForge (Business Management) plugin install pipeline."""

from __future__ import annotations

import json
from typing import Any

from src.plugins.registry import (
    is_plugin_active,
    is_plugin_installed,
    load_manifest,
    plugin_data_dir,
    read_installed_record,
    set_feature_flag,
    write_installed_record,
)


def write_default_config() -> None:
    data_dir = plugin_data_dir("sysforge")
    data_dir.mkdir(parents=True, exist_ok=True)
    config_path = data_dir / "config.json"
    if config_path.is_file():
        return
    config_path.write_text(
        json.dumps(
            {
                "tax_rate_bps": 0,
                "currency": "USD",
                "autosave_drafts": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def run_install() -> dict[str, Any]:
    manifest = load_manifest("sysforge")
    version = manifest.get("version", "0.1.0")

    if is_plugin_installed("sysforge"):
        if not is_plugin_active("sysforge"):
            set_feature_flag("sysforge", True)
        installed = read_installed_record("sysforge") or {}
        return {
            "ok": True,
            "plugin_id": "sysforge",
            "version": installed.get("version", version),
            "already_installed": True,
            "steps": [{"step": "marker", "status": "ok", "message": "Already installed"}],
            "reload_required": False,
        }

    steps: list[dict[str, str]] = []

    data_dir = plugin_data_dir("sysforge")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "drafts").mkdir(exist_ok=True)
    (data_dir / "backups").mkdir(exist_ok=True)
    steps.append({"step": "prepare", "status": "ok", "message": "Plugin data directory ready"})

    # Fresh empty SQLite DB placeholder — full migrations land with feature ports.
    db_path = data_dir / "sysforge.db"
    if not db_path.is_file():
        db_path.touch()
    steps.append({"step": "database", "status": "ok", "message": "Business database initialized"})

    write_default_config()
    steps.append({"step": "config", "status": "ok", "message": "Default config written"})

    write_installed_record("sysforge", version)
    steps.append({"step": "marker", "status": "ok", "message": "Install marker written"})

    set_feature_flag("sysforge", True)
    steps.append({"step": "feature", "status": "ok", "message": "Business Management feature enabled"})

    return {
        "ok": True,
        "plugin_id": "sysforge",
        "version": version,
        "steps": steps,
        "reload_required": False,
    }
