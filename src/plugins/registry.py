"""Discover, validate, and track optional Odysseus plugins (Finance, SysForge, …)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.constants import DATA_DIR
from src.runtime_paths import get_app_root

logger = logging.getLogger(__name__)

INTEGRATIONS_ROOT = Path(get_app_root()) / "integrations"
PLUGINS_DATA_ROOT = Path(DATA_DIR) / "plugins"

KNOWN_PLUGINS = ("finance", "sysforge")


def bundled_plugin_dir(plugin_id: str) -> Path:
    return INTEGRATIONS_ROOT / plugin_id


def plugin_data_dir(plugin_id: str) -> Path:
    return PLUGINS_DATA_ROOT / plugin_id


def installed_marker_path(plugin_id: str) -> Path:
    return plugin_data_dir(plugin_id) / "installed.json"


def is_plugin_installed(plugin_id: str) -> bool:
    return installed_marker_path(plugin_id).is_file()


def is_plugin_active(plugin_id: str) -> bool:
    """True when installed.json exists and the plugin feature flag is enabled."""
    if not is_plugin_installed(plugin_id):
        return False
    try:
        manifest = load_manifest(plugin_id)
    except (FileNotFoundError, ValueError, json.JSONDecodeError):
        return False
    from src.settings import load_features

    flag = manifest.get("feature_flag", plugin_id)
    return bool(load_features().get(flag))


def read_installed_record(plugin_id: str) -> dict[str, Any] | None:
    path = installed_marker_path(plugin_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("invalid installed.json for %s: %s", plugin_id, exc)
        return None


def load_manifest(plugin_id: str) -> dict[str, Any]:
    manifest_path = bundled_plugin_dir(plugin_id) / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Plugin manifest not found: {plugin_id}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("id") != plugin_id:
        raise ValueError(f"Manifest id mismatch for {plugin_id}")
    return data


def list_catalog() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for plugin_id in KNOWN_PLUGINS:
        bundled = bundled_plugin_dir(plugin_id)
        if not bundled.is_dir():
            continue
        try:
            manifest = load_manifest(plugin_id)
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            continue
        installed = read_installed_record(plugin_id)
        items.append({
            "id": plugin_id,
            "name": manifest.get("name", plugin_id),
            "description": manifest.get("description", ""),
            "version": manifest.get("version", "0.0.0"),
            "installed": installed is not None,
            "installed_version": (installed or {}).get("version"),
            "installed_at": (installed or {}).get("installed_at"),
            "feature_flag": manifest.get("feature_flag", plugin_id),
        })
    return items


def plugin_status(plugin_id: str) -> dict[str, Any]:
    manifest = load_manifest(plugin_id)
    installed = read_installed_record(plugin_id)
    from src.settings import load_features
    flag = manifest.get("feature_flag", plugin_id)
    features = load_features()
    return {
        "id": plugin_id,
        "name": manifest.get("name", plugin_id),
        "description": manifest.get("description", ""),
        "version": manifest.get("version", "0.0.0"),
        "installed": installed is not None,
        "installed_version": (installed or {}).get("version"),
        "installed_at": (installed or {}).get("installed_at"),
        "feature_flag": flag,
        "feature_enabled": bool(features.get(flag)),
    }


def write_installed_record(plugin_id: str, version: str, *, source: str = "bundled") -> None:
    data_dir = plugin_data_dir(plugin_id)
    data_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "plugin_id": plugin_id,
        "version": version,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    installed_marker_path(plugin_id).write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )


def remove_installed_record(plugin_id: str) -> None:
    path = installed_marker_path(plugin_id)
    if path.is_file():
        path.unlink()


def set_feature_flag(plugin_id: str, enabled: bool) -> None:
    from src.settings import load_features, save_features
    manifest = load_manifest(plugin_id)
    flag = manifest.get("feature_flag", plugin_id)
    features = load_features()
    features[flag] = enabled
    save_features(features)


def list_installed_plugin_ids() -> list[str]:
    return [pid for pid in KNOWN_PLUGINS if is_plugin_installed(pid)]
