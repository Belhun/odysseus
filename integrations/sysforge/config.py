"""Business plugin config.json — tax / currency / autosave.

Path: ``plugin_data_dir("sysforge") / config.json``.
Unknown keys are preserved on save for forward compatibility.
"""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from integrations.sysforge.db import money
from src.plugins import registry

DEFAULTS: dict[str, Any] = {
    "tax_rate_bps": 775,
    "currency": "USD",
    "autosave_drafts": True,
    "autosave_interval_seconds": 60,
    # DRAFT-08: auto_delete_old defaults false; never purge on install/startup.
    "drafts": {
        "folder_path": None,
        "retention_months": 6,
        "auto_delete_old": False,
        "schedule_enabled": False,
        "schedule_interval_days": 7,
        "last_cleanup_at": None,
        "last_cleanup_deleted": 0,
    },
    # Business backup schedule (plugin-scoped; not Odysseus /api/export).
    "backup": {
        "schedule_enabled": False,
        "schedule_interval_days": 7,
        "retention_days": 30,
        "include_drafts": False,
        "last_run_at": None,
    },
    "projects": {
        "include_archived_in_search": False,
    },
    # Future UI / MRU shell polish (VI1 column; VI2 nav persist = no)
    "dashboard_favorites": [],
    "client_mru_autoselect": True,
    # S5 mobile companion (LAN browser + inbox + optional public URL)
    "companion": {
        "enabled": True,
        "session_hours": 48,
        "pair_code_minutes": 15,
        "inbox_enabled": False,
        "inbox_path": None,
        "inbox_auto_import": False,
        "public_base_url": None,
    },
}

CURRENCY_ALLOWLIST = frozenset({"USD", "CAD", "EUR", "GBP"})
TAX_BPS_MIN = 0
TAX_BPS_MAX = 10000  # 0%–100.00%
RETENTION_MONTHS_MIN = 1
RETENTION_MONTHS_MAX = 60


def clamp_retention_months(value: Any) -> int:
    """Clamp draft retention months to [1, 60]; invalid → 6."""
    try:
        months = int(value)
    except (TypeError, ValueError):
        months = 6
    if months < RETENTION_MONTHS_MIN:
        return RETENTION_MONTHS_MIN
    if months > RETENTION_MONTHS_MAX:
        return RETENTION_MONTHS_MAX
    return months


class ConfigValidationError(ValueError):
    """Invalid business config field."""


def config_path() -> Path:
    return registry.plugin_data_dir("sysforge") / "config.json"


def tax_percent_from_bps(bps: int) -> float:
    return float(money.from_basis_points(int(bps)))


def tax_bps_from_percent(percent: float | Decimal | str | int) -> int:
    return money.to_basis_points(percent)


def _read_raw(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def load_config() -> dict[str, Any]:
    """Load config merged with defaults (does not write)."""
    path = config_path()
    raw = _read_raw(path)
    merged = {**DEFAULTS, **raw}
    # Normalize known types lightly
    try:
        merged["tax_rate_bps"] = int(merged["tax_rate_bps"])
    except (TypeError, ValueError):
        merged["tax_rate_bps"] = DEFAULTS["tax_rate_bps"]
    merged["currency"] = str(merged.get("currency") or DEFAULTS["currency"]).upper()
    merged["autosave_drafts"] = bool(merged.get("autosave_drafts", DEFAULTS["autosave_drafts"]))
    try:
        interval = int(merged.get("autosave_interval_seconds", 60))
    except (TypeError, ValueError):
        interval = 60
    if interval < 5:
        interval = 5
    if interval > 3600:
        interval = 3600
    merged["autosave_interval_seconds"] = interval

    drafts_default = DEFAULTS["drafts"]
    raw_drafts = raw.get("drafts") if isinstance(raw.get("drafts"), dict) else {}
    drafts = {**drafts_default, **raw_drafts}
    drafts["retention_months"] = clamp_retention_months(
        drafts.get("retention_months", 6)
    )
    # Missing key → false (never inherit desktop AutoDeleteOld=true).
    drafts["auto_delete_old"] = bool(drafts.get("auto_delete_old", False))
    drafts["schedule_enabled"] = bool(drafts.get("schedule_enabled", False))
    try:
        interval = int(drafts.get("schedule_interval_days", 7))
    except (TypeError, ValueError):
        interval = 7
    drafts["schedule_interval_days"] = max(1, min(365, interval))
    try:
        drafts["last_cleanup_deleted"] = int(drafts.get("last_cleanup_deleted", 0))
    except (TypeError, ValueError):
        drafts["last_cleanup_deleted"] = 0
    last_at = drafts.get("last_cleanup_at")
    drafts["last_cleanup_at"] = last_at if last_at else None
    folder = drafts.get("folder_path")
    if folder is not None and str(folder).strip() == "":
        folder = None
    drafts["folder_path"] = folder
    merged["drafts"] = drafts

    backup_default = DEFAULTS["backup"]
    raw_backup = raw.get("backup") if isinstance(raw.get("backup"), dict) else {}
    backup = {**backup_default, **raw_backup}
    try:
        backup["schedule_interval_days"] = int(backup.get("schedule_interval_days", 7))
    except (TypeError, ValueError):
        backup["schedule_interval_days"] = 7
    try:
        backup["retention_days"] = int(backup.get("retention_days", 30))
    except (TypeError, ValueError):
        backup["retention_days"] = 30
    backup["schedule_enabled"] = bool(backup.get("schedule_enabled", False))
    backup["include_drafts"] = bool(backup.get("include_drafts", False))
    merged["backup"] = backup

    projects_default = DEFAULTS["projects"]
    raw_projects = raw.get("projects") if isinstance(raw.get("projects"), dict) else {}
    projects = {**projects_default, **raw_projects}
    projects["include_archived_in_search"] = bool(
        projects.get("include_archived_in_search", False)
    )
    merged["projects"] = projects

    favs = merged.get("dashboard_favorites", DEFAULTS["dashboard_favorites"])
    if not isinstance(favs, list):
        favs = []
    cleaned_favs: list[str] = []
    seen_fav: set[str] = set()
    for item in favs:
        key = str(item or "").strip()
        if not key or key in seen_fav:
            continue
        seen_fav.add(key)
        cleaned_favs.append(key)
    merged["dashboard_favorites"] = cleaned_favs
    merged["client_mru_autoselect"] = bool(
        merged.get("client_mru_autoselect", DEFAULTS["client_mru_autoselect"])
    )

    companion_default = DEFAULTS["companion"]
    raw_companion = raw.get("companion") if isinstance(raw.get("companion"), dict) else {}
    companion = {**companion_default, **raw_companion}
    companion["enabled"] = bool(companion.get("enabled", True))
    companion["inbox_enabled"] = bool(companion.get("inbox_enabled", False))
    companion["inbox_auto_import"] = bool(companion.get("inbox_auto_import", False))
    try:
        companion["session_hours"] = max(
            1, min(168, int(companion.get("session_hours", 48)))
        )
    except (TypeError, ValueError):
        companion["session_hours"] = 48
    try:
        companion["pair_code_minutes"] = max(
            1, min(120, int(companion.get("pair_code_minutes", 15)))
        )
    except (TypeError, ValueError):
        companion["pair_code_minutes"] = 15
    inbox_path = companion.get("inbox_path")
    if inbox_path is not None and str(inbox_path).strip() == "":
        inbox_path = None
    companion["inbox_path"] = inbox_path
    public = companion.get("public_base_url")
    if public is not None:
        public = str(public).strip().rstrip("/") or None
    companion["public_base_url"] = public
    merged["companion"] = companion
    return merged


def validate_partial(partial: dict[str, Any]) -> dict[str, Any]:
    """Validate a partial update; return cleaned keys only."""
    if not isinstance(partial, dict):
        raise ConfigValidationError("Body must be a JSON object")

    cleaned: dict[str, Any] = {}

    has_percent = "tax_rate_percent" in partial and partial["tax_rate_percent"] is not None
    has_bps = "tax_rate_bps" in partial and partial["tax_rate_bps"] is not None

    if has_percent and has_bps:
        try:
            bps_from_percent = tax_bps_from_percent(partial["tax_rate_percent"])
            bps_direct = int(partial["tax_rate_bps"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError("Invalid tax rate") from exc
        if bps_from_percent != bps_direct:
            raise ConfigValidationError(
                "tax_rate_percent and tax_rate_bps disagree"
            )
        cleaned["tax_rate_bps"] = bps_direct
    elif has_percent:
        try:
            percent = float(partial["tax_rate_percent"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError("tax_rate_percent must be a number") from exc
        if percent < 0 or percent > 100:
            raise ConfigValidationError("tax_rate_percent must be between 0 and 100")
        cleaned["tax_rate_bps"] = tax_bps_from_percent(percent)
    elif has_bps:
        try:
            bps = int(partial["tax_rate_bps"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError("tax_rate_bps must be an integer") from exc
        if bps < TAX_BPS_MIN or bps > TAX_BPS_MAX:
            raise ConfigValidationError(
                f"tax_rate_bps must be between {TAX_BPS_MIN} and {TAX_BPS_MAX}"
            )
        cleaned["tax_rate_bps"] = bps

    if "currency" in partial and partial["currency"] is not None:
        currency = str(partial["currency"]).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ConfigValidationError("currency must be a 3-letter ISO code")
        if currency not in CURRENCY_ALLOWLIST:
            raise ConfigValidationError(
                f"currency must be one of: {', '.join(sorted(CURRENCY_ALLOWLIST))}"
            )
        cleaned["currency"] = currency

    if "autosave_drafts" in partial and partial["autosave_drafts"] is not None:
        if not isinstance(partial["autosave_drafts"], bool):
            raise ConfigValidationError("autosave_drafts must be a boolean")
        cleaned["autosave_drafts"] = partial["autosave_drafts"]

    if (
        "autosave_interval_seconds" in partial
        and partial["autosave_interval_seconds"] is not None
    ):
        try:
            interval = int(partial["autosave_interval_seconds"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(
                "autosave_interval_seconds must be an integer"
            ) from exc
        if interval < 5 or interval > 3600:
            raise ConfigValidationError(
                "autosave_interval_seconds must be between 5 and 3600"
            )
        cleaned["autosave_interval_seconds"] = interval

    if "projects" in partial and partial["projects"] is not None:
        if not isinstance(partial["projects"], dict):
            raise ConfigValidationError("projects must be an object")
        proj: dict[str, Any] = {}
        if "include_archived_in_search" in partial["projects"]:
            flag = partial["projects"]["include_archived_in_search"]
            if not isinstance(flag, bool):
                raise ConfigValidationError(
                    "projects.include_archived_in_search must be a boolean"
                )
            proj["include_archived_in_search"] = flag
        if proj:
            cleaned["projects"] = proj

    if "dashboard_favorites" in partial and partial["dashboard_favorites"] is not None:
        raw_favs = partial["dashboard_favorites"]
        if not isinstance(raw_favs, list):
            raise ConfigValidationError("dashboard_favorites must be an array")
        favs: list[str] = []
        seen: set[str] = set()
        for item in raw_favs:
            key = str(item or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            favs.append(key)
        cleaned["dashboard_favorites"] = favs

    if (
        "client_mru_autoselect" in partial
        and partial["client_mru_autoselect"] is not None
    ):
        if not isinstance(partial["client_mru_autoselect"], bool):
            raise ConfigValidationError("client_mru_autoselect must be a boolean")
        cleaned["client_mru_autoselect"] = partial["client_mru_autoselect"]

    if (
        "include_archived_in_search" in partial
        and partial["include_archived_in_search"] is not None
    ):
        if not isinstance(partial["include_archived_in_search"], bool):
            raise ConfigValidationError(
                "include_archived_in_search must be a boolean"
            )
        cleaned["projects"] = {
            **cleaned.get("projects", {}),
            "include_archived_in_search": partial["include_archived_in_search"],
        }

    if "drafts" in partial and partial["drafts"] is not None:
        if not isinstance(partial["drafts"], dict):
            raise ConfigValidationError("drafts must be an object")
        drafts_partial = validate_drafts_retention(partial["drafts"])
        if drafts_partial:
            cleaned["drafts"] = drafts_partial

    if "companion" in partial and partial["companion"] is not None:
        if not isinstance(partial["companion"], dict):
            raise ConfigValidationError("companion must be an object")
        companion_partial = validate_companion(partial["companion"])
        if companion_partial:
            cleaned["companion"] = companion_partial

    return cleaned


def validate_companion(partial: dict[str, Any]) -> dict[str, Any]:
    """Validate companion settings partial; return cleaned keys only."""
    if not isinstance(partial, dict):
        raise ConfigValidationError("companion body must be an object")

    cleaned: dict[str, Any] = {}

    for key in ("enabled", "inbox_enabled", "inbox_auto_import"):
        if key in partial and partial[key] is not None:
            if not isinstance(partial[key], bool):
                raise ConfigValidationError(f"{key} must be a boolean")
            cleaned[key] = partial[key]

    if "session_hours" in partial and partial["session_hours"] is not None:
        try:
            hours = int(partial["session_hours"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError("session_hours must be an integer") from exc
        if hours < 1 or hours > 168:
            raise ConfigValidationError("session_hours must be between 1 and 168")
        cleaned["session_hours"] = hours

    if "pair_code_minutes" in partial and partial["pair_code_minutes"] is not None:
        try:
            minutes = int(partial["pair_code_minutes"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(
                "pair_code_minutes must be an integer"
            ) from exc
        if minutes < 1 or minutes > 120:
            raise ConfigValidationError(
                "pair_code_minutes must be between 1 and 120"
            )
        cleaned["pair_code_minutes"] = minutes

    if "inbox_path" in partial:
        raw_path = partial["inbox_path"]
        if raw_path is None or str(raw_path).strip() == "":
            cleaned["inbox_path"] = None
        else:
            cleaned["inbox_path"] = str(raw_path).strip()

    if "public_base_url" in partial:
        raw_url = partial["public_base_url"]
        if raw_url is None or str(raw_url).strip() == "":
            cleaned["public_base_url"] = None
        else:
            url = str(raw_url).strip().rstrip("/")
            if not (
                url.startswith("http://")
                or url.startswith("https://")
            ):
                raise ConfigValidationError(
                    "public_base_url must start with http:// or https://"
                )
            cleaned["public_base_url"] = url

    return cleaned


def validate_drafts_retention(partial: dict[str, Any]) -> dict[str, Any]:
    """Validate draft retention settings partial; return cleaned keys only."""
    if not isinstance(partial, dict):
        raise ConfigValidationError("drafts retention body must be an object")

    cleaned: dict[str, Any] = {}

    if "auto_delete_old" in partial and partial["auto_delete_old"] is not None:
        if not isinstance(partial["auto_delete_old"], bool):
            raise ConfigValidationError("auto_delete_old must be a boolean")
        cleaned["auto_delete_old"] = partial["auto_delete_old"]

    if "retention_months" in partial and partial["retention_months"] is not None:
        try:
            months = int(partial["retention_months"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(
                "retention_months must be an integer"
            ) from exc
        cleaned["retention_months"] = clamp_retention_months(months)

    if "schedule_enabled" in partial and partial["schedule_enabled"] is not None:
        if not isinstance(partial["schedule_enabled"], bool):
            raise ConfigValidationError("schedule_enabled must be a boolean")
        cleaned["schedule_enabled"] = partial["schedule_enabled"]

    if (
        "schedule_interval_days" in partial
        and partial["schedule_interval_days"] is not None
    ):
        try:
            interval = int(partial["schedule_interval_days"])
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError(
                "schedule_interval_days must be an integer"
            ) from exc
        if interval < 1 or interval > 365:
            raise ConfigValidationError(
                "schedule_interval_days must be between 1 and 365"
            )
        cleaned["schedule_interval_days"] = interval

    return cleaned


def save_drafts_retention(partial: dict[str, Any]) -> dict[str, Any]:
    """Merge draft retention keys into config.json; return drafts block."""
    cleaned = validate_drafts_retention(partial)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    raw = _read_raw(path)
    base_drafts = DEFAULTS["drafts"]
    raw_drafts = raw.get("drafts") if isinstance(raw.get("drafts"), dict) else {}
    drafts = {**base_drafts, **raw_drafts, **cleaned}
    drafts["retention_months"] = clamp_retention_months(
        drafts.get("retention_months", 6)
    )
    drafts["auto_delete_old"] = bool(drafts.get("auto_delete_old", False))

    merged = {**DEFAULTS, **raw, "drafts": drafts}
    if isinstance(raw.get("backup"), dict):
        merged["backup"] = {**DEFAULTS["backup"], **raw["backup"]}
    if isinstance(raw.get("projects"), dict):
        merged["projects"] = {**DEFAULTS["projects"], **raw["projects"]}

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    return load_config()["drafts"]


def record_draft_cleanup(deleted: int, at_iso: str | None = None) -> dict[str, Any]:
    """Persist last cleanup metadata after a retention run."""
    from integrations.sysforge.db import utc

    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _read_raw(path)
    base_drafts = DEFAULTS["drafts"]
    raw_drafts = raw.get("drafts") if isinstance(raw.get("drafts"), dict) else {}
    drafts = {
        **base_drafts,
        **raw_drafts,
        "last_cleanup_at": at_iso or utc.format_storage(),
        "last_cleanup_deleted": int(deleted),
    }
    merged = {**DEFAULTS, **raw, "drafts": drafts}
    if isinstance(raw.get("backup"), dict):
        merged["backup"] = {**DEFAULTS["backup"], **raw["backup"]}
    if isinstance(raw.get("projects"), dict):
        merged["projects"] = {**DEFAULTS["projects"], **raw["projects"]}

    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    return load_config()["drafts"]


def save_config(partial: dict[str, Any]) -> dict[str, Any]:
    """Validate partial update, merge, atomic write; return full merged config."""
    cleaned = validate_partial(partial)
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    raw = _read_raw(path)
    # Start from defaults + existing, apply cleaned known keys
    merged = {**DEFAULTS, **raw, **cleaned}
    if "drafts" in cleaned:
        base_drafts = DEFAULTS["drafts"]
        raw_drafts = raw.get("drafts") if isinstance(raw.get("drafts"), dict) else {}
        merged["drafts"] = {**base_drafts, **raw_drafts, **cleaned["drafts"]}
    elif isinstance(raw.get("drafts"), dict):
        base_drafts = DEFAULTS["drafts"]
        merged["drafts"] = {**base_drafts, **raw["drafts"]}
    # Preserve backup schedule block unless an explicit writer updates it
    if isinstance(raw.get("backup"), dict) and "backup" not in cleaned:
        base_backup = DEFAULTS["backup"]
        merged["backup"] = {**base_backup, **raw["backup"]}
    if "projects" in cleaned:
        base_projects = DEFAULTS["projects"]
        raw_projects = raw.get("projects") if isinstance(raw.get("projects"), dict) else {}
        merged["projects"] = {**base_projects, **raw_projects, **cleaned["projects"]}
    elif isinstance(raw.get("projects"), dict):
        merged["projects"] = {**DEFAULTS["projects"], **raw["projects"]}
    if "companion" in cleaned:
        base_companion = DEFAULTS["companion"]
        raw_companion = (
            raw.get("companion") if isinstance(raw.get("companion"), dict) else {}
        )
        merged["companion"] = {
            **base_companion,
            **raw_companion,
            **cleaned["companion"],
        }
    elif isinstance(raw.get("companion"), dict):
        merged["companion"] = {**DEFAULTS["companion"], **raw["companion"]}

    # Atomic replace
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(merged, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise

    return load_config()


def settings_response(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    data = cfg if cfg is not None else load_config()
    bps = int(data["tax_rate_bps"])
    drafts = data.get("drafts") if isinstance(data.get("drafts"), dict) else {}
    projects = data.get("projects") if isinstance(data.get("projects"), dict) else {}
    companion = data.get("companion") if isinstance(data.get("companion"), dict) else {}
    include_archived = bool(projects.get("include_archived_in_search", False))
    return {
        "ok": True,
        "tax_rate_bps": bps,
        "tax_rate_percent": tax_percent_from_bps(bps),
        "currency": data["currency"],
        "autosave_drafts": bool(data["autosave_drafts"]),
        "autosave_interval_seconds": int(data.get("autosave_interval_seconds", 60)),
        "drafts": {
            "retention_months": clamp_retention_months(
                drafts.get("retention_months", 6)
            ),
            "auto_delete_old": bool(drafts.get("auto_delete_old", False)),
            "schedule_enabled": bool(drafts.get("schedule_enabled", False)),
            "schedule_interval_days": int(drafts.get("schedule_interval_days", 7)),
            "last_cleanup_at": drafts.get("last_cleanup_at"),
            "last_cleanup_deleted": int(drafts.get("last_cleanup_deleted", 0) or 0),
        },
        "projects": {
            "include_archived_in_search": include_archived,
        },
        "include_archived_in_search": include_archived,
        "dashboard_favorites": list(data.get("dashboard_favorites") or []),
        "client_mru_autoselect": bool(data.get("client_mru_autoselect", True)),
        "companion": {
            "enabled": bool(companion.get("enabled", True)),
            "session_hours": int(companion.get("session_hours", 48)),
            "pair_code_minutes": int(companion.get("pair_code_minutes", 15)),
            "inbox_enabled": bool(companion.get("inbox_enabled", False)),
            "inbox_path": companion.get("inbox_path"),
            "inbox_auto_import": bool(companion.get("inbox_auto_import", False)),
            "public_base_url": companion.get("public_base_url"),
        },
    }
