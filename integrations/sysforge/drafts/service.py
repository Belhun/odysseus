"""File DraftService — JSON under plugin drafts folder (desktop parity).

DRAFT-08: retention cleanup is optional (default off). Call only from
settings / scheduled gate — never from install, startup, or import.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dateutil.relativedelta import relativedelta

from integrations.sysforge.config import (
    clamp_retention_months,
    load_config,
    record_draft_cleanup,
)
from integrations.sysforge.db import utc
from integrations.sysforge.drafts.models import (
    AUTOSAVE_NAME,
    coerce_draft,
    generate_default_name_from_draft,
    normalize_draft_name,
    parse_last_modified,
)
from src.plugins import registry

logger = logging.getLogger(__name__)

CANDIDATES_PREVIEW_CAP = 20


def drafts_folder(config: dict[str, Any] | None = None) -> Path:
    """Resolve drafts root: config ``drafts.folder_path`` or plugin data ``drafts/``."""
    cfg = config if config is not None else load_config()
    drafts_cfg = cfg.get("drafts") if isinstance(cfg.get("drafts"), dict) else {}
    custom = drafts_cfg.get("folder_path") if drafts_cfg else None
    if custom and str(custom).strip():
        path = Path(str(custom).strip())
    else:
        path = registry.plugin_data_dir("sysforge") / "drafts"
    path.mkdir(parents=True, exist_ok=True)
    return path


class DraftService:
    """Async-friendly sync I/O service with process-local write lock + list cache."""

    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder if folder is not None else drafts_folder()
        self._folder.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._autosave_cycle = 0
        self._cache: list[dict[str, Any]] | None = None
        self._cache_last_updated: datetime = datetime.min.replace(tzinfo=timezone.utc)

    @property
    def folder(self) -> Path:
        return self._folder

    def _invalidate_cache(self) -> None:
        self._cache = None
        self._cache_last_updated = datetime.min.replace(tzinfo=timezone.utc)

    def _is_cache_valid(self) -> bool:
        if self._cache is None:
            return False
        try:
            draft_files = list(self._folder.glob("draft_*.json"))
            autosave_files = list(self._folder.glob("autosave_*.json"))
            total = len(draft_files) + len(autosave_files)
            # Cache may omit saved autosaves — compare against listed count loosely
            if total < len(self._cache):
                return False
            for path in draft_files + autosave_files:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                if mtime > self._cache_last_updated:
                    return False
            return True
        except OSError:
            return False

    def _atomic_write(self, file_path: Path, draft: dict[str, Any]) -> None:
        payload = {k: v for k, v in draft.items() if k != "filePath"}
        fd, tmp_name = tempfile.mkstemp(
            dir=str(file_path.parent),
            prefix=f".{file_path.stem}-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            os.replace(tmp_name, file_path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _try_load(self, file_path: Path) -> dict[str, Any] | None:
        if not file_path.is_file():
            return None
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            draft = coerce_draft(raw)
            normalize_draft_name(draft)
            draft["filePath"] = str(file_path)
            return draft
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Failed to load draft file %s: %s", file_path, exc)
            return None

    def get_all_drafts(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._cache is not None and self._is_cache_valid():
                return list(self._cache)

            drafts: list[dict[str, Any]] = []
            for path in sorted(self._folder.glob("draft_*.json")):
                draft = self._try_load(path)
                if draft is not None:
                    drafts.append(draft)

            for path in sorted(self._folder.glob("autosave_*.json")):
                draft = self._try_load(path)
                if draft is None:
                    continue
                if draft.get("invoiceWasSaved"):
                    continue
                if not (draft.get("name") or "").strip():
                    draft["name"] = AUTOSAVE_NAME
                drafts.append(draft)

            drafts.sort(key=parse_last_modified, reverse=True)
            self._cache = drafts
            self._cache_last_updated = utc.utc_now()
            return list(drafts)

    def save_draft(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        if raw is None:
            raise ValueError("draft is required")
        draft = coerce_draft(raw)
        with self._lock:
            if not draft.get("id"):
                draft["id"] = str(uuid.uuid4())
                draft["createdAt"] = draft.get("createdAt") or _now_iso()
            draft["lastModifiedAt"] = _now_iso()
            draft["isAutosave"] = False
            normalize_draft_name(draft)
            file_path = self._folder / f"draft_{draft['id']}.json"
            self._atomic_write(file_path, draft)
            draft["filePath"] = str(file_path)
            self._invalidate_cache()
            return draft

    def save_autosave(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        if raw is None:
            raise ValueError("draft is required")
        draft = coerce_draft(raw)
        with self._lock:
            self._autosave_cycle += 1
            slot = (self._autosave_cycle % 3) + 1
            draft["lastModifiedAt"] = _now_iso()
            draft["isAutosave"] = True
            draft["name"] = AUTOSAVE_NAME
            if not draft.get("id"):
                draft["id"] = str(uuid.uuid4())
            if not draft.get("createdAt"):
                draft["createdAt"] = draft["lastModifiedAt"]
            file_path = self._folder / f"autosave_{slot}.json"
            self._atomic_write(file_path, draft)
            draft["filePath"] = str(file_path)
            self._invalidate_cache()
            return draft

    def load_autosave(self) -> dict[str, Any] | None:
        with self._lock:
            autosaves: list[dict[str, Any]] = []
            for i in range(1, 4):
                draft = self._try_load(self._folder / f"autosave_{i}.json")
                if draft is not None:
                    autosaves.append(draft)
            if not autosaves:
                return None
            autosaves.sort(key=parse_last_modified, reverse=True)
            return autosaves[0]

    def load_draft(self, file_path: str | Path) -> dict[str, Any] | None:
        return self._try_load(Path(file_path))

    def load_draft_by_id(self, draft_id: str) -> dict[str, Any] | None:
        if not draft_id or not str(draft_id).strip():
            return None
        return self._try_load(self._folder / f"draft_{draft_id}.json")

    def rename_draft(self, draft_id: str, new_name: str | None) -> dict[str, Any]:
        draft = self.load_draft_by_id(draft_id)
        if draft is None:
            raise FileNotFoundError(f"Draft with ID {draft_id} not found")
        trimmed = (new_name or "").strip()
        draft["name"] = (
            generate_default_name_from_draft(draft) if not trimmed else trimmed
        )
        draft["lastModifiedAt"] = _now_iso()
        return self.save_draft(draft)

    def delete_draft(self, draft_id: str) -> bool:
        with self._lock:
            file_path = self._folder / f"draft_{draft_id}.json"
            existed = file_path.is_file()
            if existed:
                try:
                    file_path.unlink()
                except OSError:
                    return False
            self._invalidate_cache()
            return existed

    def delete_drafts(self, ids: list[str]) -> int:
        deleted = 0
        for draft_id in ids:
            try:
                if self.delete_draft(draft_id):
                    deleted += 1
            except Exception:
                continue
        return deleted

    def clear_autosaves(self) -> None:
        with self._lock:
            for i in range(1, 4):
                path = self._folder / f"autosave_{i}.json"
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass
            self._invalidate_cache()

    def retention_settings(self) -> tuple[int, bool]:
        """Return (retention_months, auto_delete_old). Odysseus default: off."""
        cfg = load_config()
        drafts_cfg = cfg.get("drafts") if isinstance(cfg.get("drafts"), dict) else {}
        months = clamp_retention_months(
            drafts_cfg.get("retention_months", 6) if drafts_cfg else 6
        )
        auto = bool(drafts_cfg.get("auto_delete_old", False)) if drafts_cfg else False
        return months, auto

    def get_retention_config(self) -> dict[str, Any]:
        """Current retention settings + last-run metadata."""
        cfg = load_config()
        drafts = cfg.get("drafts") if isinstance(cfg.get("drafts"), dict) else {}
        months, auto = self.retention_settings()
        try:
            interval = int(drafts.get("schedule_interval_days", 7))
        except (TypeError, ValueError):
            interval = 7
        return {
            "auto_delete_old": auto,
            "retention_months": months,
            "schedule_enabled": bool(drafts.get("schedule_enabled", False)),
            "schedule_interval_days": max(1, min(365, interval)),
            "last_cleanup_at": drafts.get("last_cleanup_at"),
            "last_cleanup_deleted": int(drafts.get("last_cleanup_deleted", 0) or 0),
        }

    def preview_old_drafts(
        self, retention_months: int | None = None
    ) -> dict[str, Any]:
        """Read-only: what cleanup would delete under current months (even if off)."""
        months, auto = self.retention_settings()
        if retention_months is not None:
            months = clamp_retention_months(retention_months)
        candidates, skipped_pinned, skipped_autosave, _ = self._classify_retention(
            months=months
        )
        sample = []
        for draft in candidates[:CANDIDATES_PREVIEW_CAP]:
            sample.append(
                {
                    "id": draft.get("id") or "",
                    "name": draft.get("name") or "",
                    "last_modified_at": draft.get("lastModifiedAt"),
                    "pinned": bool(draft.get("pinned")),
                }
            )
        return {
            "auto_delete_old": auto,
            "retention_months": months,
            "would_delete": len(candidates),
            "candidates": sample,
            "skipped_pinned": skipped_pinned,
            "skipped_autosave": skipped_autosave,
        }

    def _classify_retention(
        self,
        months: int | None = None,
    ) -> tuple[list[dict[str, Any]], int, int, int]:
        """Return (candidates, skipped_pinned, skipped_autosave, retention_months)."""
        if months is None:
            retention_months, _ = self.retention_settings()
        else:
            retention_months = clamp_retention_months(months)
        cutoff = utc.utc_now() - relativedelta(months=retention_months)
        candidates: list[dict[str, Any]] = []
        skipped_pinned = 0
        skipped_autosave = 0
        for draft in self.get_all_drafts():
            if draft.get("isAutosave"):
                skipped_autosave += 1
                continue
            modified = parse_last_modified(draft)
            if modified >= cutoff:
                continue
            if draft.get("pinned"):
                skipped_pinned += 1
                continue
            candidates.append(draft)
        return candidates, skipped_pinned, skipped_autosave, retention_months

    def cleanup_old_drafts(self) -> dict[str, Any]:
        """Delete eligible old named drafts when auto_delete_old is true.

        Toggle is the master switch. No force bypass. Do not call from startup.
        """
        months, auto_delete_old = self.retention_settings()
        if not auto_delete_old:
            return {
                "deleted": 0,
                "skipped_pinned": 0,
                "skipped_autosave": 0,
                "retention_months": months,
                "reason": "disabled",
                "notice": None,
            }

        candidates, skipped_pinned, skipped_autosave, _ = self._classify_retention()
        deleted = 0
        with self._lock:
            for draft in candidates:
                file_path = draft.get("filePath")
                if not file_path:
                    continue
                path = Path(file_path)
                try:
                    if path.is_file():
                        path.unlink()
                        deleted += 1
                except OSError:
                    continue
            if deleted:
                self._invalidate_cache()

        notice = None
        if deleted > 0:
            notice = (
                f"Removed {deleted} old draft(s) "
                f"(older than {months} months)."
            )
            record_draft_cleanup(deleted)
        else:
            record_draft_cleanup(0)

        return {
            "deleted": deleted,
            "skipped_pinned": skipped_pinned,
            "skipped_autosave": skipped_autosave,
            "retention_months": months,
            "reason": None,
            "notice": notice,
        }

    def delete_old_drafts(self) -> int:
        """Delete manual drafts older than retention when auto_delete_old is true.

        Do not call from startup; see ``draft-retention-draft-08``.
        """
        return int(self.cleanup_old_drafts()["deleted"])

    def set_pinned(self, draft_id: str, pinned: bool) -> dict[str, Any]:
        """Set keep-forever pin on a named draft. Autosaves cannot be pinned."""
        if not draft_id or not str(draft_id).strip():
            raise FileNotFoundError("Draft not found")
        draft = self.load_draft_by_id(draft_id)
        if draft is None:
            raise FileNotFoundError(f"Draft with ID {draft_id} not found")
        if draft.get("isAutosave"):
            raise ValueError("Autosave drafts cannot be pinned")
        draft["pinned"] = bool(pinned)
        # Keep lastModifiedAt so retention age is unchanged by pin toggles.
        with self._lock:
            file_path = self._folder / f"draft_{draft['id']}.json"
            self._atomic_write(file_path, draft)
            draft["filePath"] = str(file_path)
            self._invalidate_cache()
            return draft

    def maybe_run_scheduled_retention(self) -> dict[str, Any] | None:
        """Lazy weekly cleanup when schedule_enabled and auto_delete_old.

        Safe no-op when either flag is off. Never called from install/startup.
        """
        from datetime import timedelta

        settings = self.get_retention_config()
        if not settings["auto_delete_old"]:
            return None
        if not settings["schedule_enabled"]:
            return None

        last_at = settings.get("last_cleanup_at")
        if last_at:
            try:
                last = utc.parse_storage(str(last_at))
                due = last + timedelta(days=int(settings["schedule_interval_days"]))
                if utc.utc_now() < due:
                    return None
            except (ValueError, TypeError):
                pass

        return self.cleanup_old_drafts()


def _now_iso() -> str:
    aware = utc.utc_now()
    return aware.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# Module-level singleton for routes (folder resolved at first use / after install).
_service: DraftService | None = None
_service_lock = threading.Lock()


def get_draft_service() -> DraftService:
    global _service
    with _service_lock:
        if _service is None:
            _service = DraftService()
        return _service


def reset_draft_service_for_tests(folder: Path | None = None) -> DraftService:
    """Replace singleton (tests only)."""
    global _service
    with _service_lock:
        _service = DraftService(folder=folder) if folder is not None else DraftService()
        return _service
