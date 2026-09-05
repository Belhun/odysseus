"""SysForge (Business Management) plugin install pipeline."""

from __future__ import annotations

import json
from typing import Any

from integrations.sysforge.db.exceptions import ChecksumMismatchError, MigrationError
from integrations.sysforge.db.migration_runner import ensure_schema
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
                "tax_rate_bps": 775,
                "currency": "USD",
                "autosave_drafts": True,
                "autosave_interval_seconds": 60,
                "backup_on_migration": False,
                # DRAFT-08: retention off until draft-retention-draft-08 wires UI/job.
                "drafts": {
                    "folder_path": None,
                    "retention_months": 6,
                    "auto_delete_old": False,
                    "schedule_enabled": False,
                    "schedule_interval_days": 7,
                    "last_cleanup_at": None,
                    "last_cleanup_deleted": 0,
                },
                # Plugin-scoped Business backups (not Odysseus /api/export).
                "backup": {
                    "schedule_enabled": False,
                    "schedule_interval_days": 7,
                    "retention_days": 30,
                    "include_drafts": False,
                    "last_run_at": None,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _migrate_step() -> dict[str, str]:
    """Run checksummed migrations; return a steps[] entry."""
    try:
        report = ensure_schema()
    except ChecksumMismatchError as exc:
        return {
            "step": "migrate",
            "status": "error",
            "message": str(exc),
            "error_code": exc.error_code,
        }
    except MigrationError as exc:
        return {
            "step": "migrate",
            "status": "error",
            "message": str(exc),
        }

    latest = report.latest_id if report.latest_id is not None else 0
    return {
        "step": "migrate",
        "status": "ok",
        "message": f"Schema at migration {latest:04d}",
    }


def run_install() -> dict[str, Any]:
    manifest = load_manifest("sysforge")
    version = manifest.get("version", "0.1.0")

    if is_plugin_installed("sysforge"):
        if not is_plugin_active("sysforge"):
            set_feature_flag("sysforge", True)
        installed = read_installed_record("sysforge") or {}
        migrate = _migrate_step()
        ok = migrate.get("status") == "ok"
        return {
            "ok": ok,
            "plugin_id": "sysforge",
            "version": installed.get("version", version),
            "already_installed": True,
            "steps": [
                {"step": "marker", "status": "ok", "message": "Already installed"},
                migrate,
            ],
            "reload_required": False,
        }

    steps: list[dict[str, str]] = []

    data_dir = plugin_data_dir("sysforge")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "drafts").mkdir(exist_ok=True)
    (data_dir / "backups").mkdir(exist_ok=True)
    steps.append({"step": "prepare", "status": "ok", "message": "Plugin data directory ready"})

    db_path = data_dir / "sysforge.db"
    if not db_path.is_file():
        db_path.touch()

    migrate = _migrate_step()
    steps.append(migrate)
    if migrate.get("status") != "ok":
        return {
            "ok": False,
            "plugin_id": "sysforge",
            "version": version,
            "steps": steps,
            "reload_required": False,
        }

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
