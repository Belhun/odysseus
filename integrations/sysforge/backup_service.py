"""SysForge-scoped backup, restore, and portable JSON import/export.

ADR: Business backup lives under ``data/plugins/sysforge/backups/`` and covers
only shop data (``sysforge.db``, plugin ``config.json``, optional drafts).
It is not Odysseus ``/api/export`` / ``/api/import`` (memories, presets, skills,
host settings). Full-host ``scripts/odysseus-backup`` may incidentally copy the
plugin folder as disaster recovery; that is not the shop-facing product.

BUG-018: after JSON import with ``import_clients`` / ``import_parts`` (even Skip /
0 imported) and after ``.db`` restore, always call ``rebuild_all_search``
(clients FTS + parts FTS). SQL dump import is intentionally not ported.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from integrations.sysforge import config as plugin_config
from integrations.sysforge.backup_models import (
    EXPORT_VERSION,
    SQL_IMPORT_REJECT_MESSAGE,
    BackupInfo,
    BackupResult,
    BackupSchedule,
    DEFAULT_BACKUP_SCHEDULE,
    ImportOptions,
    ImportResult,
    RestoreResult,
    map_discount_type,
    map_item_type,
    map_status,
)
from integrations.sysforge.db import connection as db_connection
from integrations.sysforge.db import money, utc
from integrations.sysforge.services.client_query import normalize_phone
from integrations.sysforge.services.clients import rebuild_clients_fts
from integrations.sysforge.services.parts import rebuild_parts_fts
from src.plugins import registry

logger = logging.getLogger(__name__)

_BACKUP_NAME_RE = re.compile(
    r"^sysforge-backup-\d{4}-\d{2}-\d{2}-\d{6}(?:\.zip|\.db)$",
    re.IGNORECASE,
)


class BackupError(ValueError):
    """User-facing backup / import failure."""


class UnsupportedExportVersion(BackupError):
    """exportVersion is not 1.0."""


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


def plugin_root() -> Path:
    return registry.plugin_data_dir("sysforge")


def backups_dir() -> Path:
    path = plugin_root() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def drafts_dir() -> Path:
    return plugin_root() / "drafts"


# ---------------------------------------------------------------------------
# Search rebuild (BUG-018)
# ---------------------------------------------------------------------------


def rebuild_client_search(*, reason: str) -> int:
    """Wipe + rebuild clients FTS. Never skip based on import counts."""
    count = rebuild_clients_fts()
    logger.info("Rebuilt client search (%s rows) reason=%s", count, reason)
    return count


def rebuild_parts_search(*, reason: str) -> dict[str, int]:
    """Wipe + rebuild parts FTS. Never skip based on import counts."""
    counts = rebuild_parts_fts()
    logger.info(
        "Rebuilt parts search (parts=%s fts=%s) reason=%s",
        counts.get("parts_count"),
        counts.get("fts_count"),
        reason,
    )
    return counts


def rebuild_all_search(*, reason: str) -> dict[str, Any]:
    """Rebuild client + parts FTS indexes (BUG-018 restore/import)."""
    clients = rebuild_client_search(reason=reason)
    parts = rebuild_parts_search(reason=reason)
    return {"clients_fts": clients, **parts}


# ---------------------------------------------------------------------------
# Integrity / checkpoint
# ---------------------------------------------------------------------------


def validate_database_file(path: Path | str) -> bool:
    target = Path(path)
    if not target.is_file():
        return False
    try:
        conn = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            return bool(row and str(row[0]).lower() == "ok")
        finally:
            conn.close()
    except sqlite3.Error:
        return False


def checkpoint_database(path: Path | None = None) -> None:
    target = path or db_connection.db_path()
    if not target.is_file():
        return
    conn = sqlite3.connect(str(target))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _sqlite_backup_copy(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src))
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()


# ---------------------------------------------------------------------------
# Schedule config
# ---------------------------------------------------------------------------


def load_backup_schedule() -> BackupSchedule:
    cfg = plugin_config.load_config()
    raw = cfg.get("backup") if isinstance(cfg.get("backup"), dict) else {}
    merged = {**DEFAULT_BACKUP_SCHEDULE, **raw}
    try:
        interval = int(merged.get("schedule_interval_days", 7))
    except (TypeError, ValueError):
        interval = 7
    try:
        retention = int(merged.get("retention_days", 30))
    except (TypeError, ValueError):
        retention = 30
    return BackupSchedule(
        schedule_enabled=bool(merged.get("schedule_enabled", False)),
        schedule_interval_days=max(1, min(365, interval)),
        retention_days=max(1, min(3650, retention)),
        include_drafts=bool(merged.get("include_drafts", False)),
        last_run_at=merged.get("last_run_at"),
    )


def save_backup_schedule(partial: dict[str, Any]) -> BackupSchedule:
    current = load_backup_schedule().to_dict()
    allowed = {
        "schedule_enabled",
        "schedule_interval_days",
        "retention_days",
        "include_drafts",
        "last_run_at",
    }
    for key, value in partial.items():
        if key in allowed:
            current[key] = value
    # Persist via raw merge (config.save_config only knows settings MVP keys)
    path = plugin_config.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, json.JSONDecodeError):
            raw = {}
    raw["backup"] = current
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=".config-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(raw, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return load_backup_schedule()


# ---------------------------------------------------------------------------
# Create / list / cleanup
# ---------------------------------------------------------------------------


def _timestamp_slug() -> str:
    return datetime.now().strftime("%Y-%m-%d-%H%M%S")


def _backup_id_from_filename(name: str) -> str:
    stem = Path(name).stem
    return stem


def create_backup(*, include_drafts: bool | None = None) -> BackupResult:
    """Create a ZIP under backups/ with sysforge.db, config.json, optional drafts."""
    schedule = load_backup_schedule()
    if include_drafts is None:
        include_drafts = schedule.include_drafts

    ts = _timestamp_slug()
    backup_id = f"sysforge-backup-{ts}"
    zip_name = f"{backup_id}.zip"
    zip_path = backups_dir() / zip_name

    live_db = db_connection.db_path()
    if not live_db.is_file():
        return BackupResult(success=False, message="Business database not found.")

    tmp_root = Path(tempfile.mkdtemp(prefix="sysforge-backup-"))
    try:
        checkpoint_database(live_db)
        db_copy = tmp_root / "sysforge.db"
        _sqlite_backup_copy(live_db, db_copy)
        if not validate_database_file(db_copy):
            return BackupResult(
                success=False,
                message="Backup file failed integrity check after copy.",
            )

        config_src = plugin_config.config_path()
        has_config = config_src.is_file()
        if has_config:
            shutil.copy2(config_src, tmp_root / "config.json")

        has_drafts = False
        drafts_src = drafts_dir()
        if include_drafts and drafts_src.is_dir():
            dest_drafts = tmp_root / "drafts"
            shutil.copytree(drafts_src, dest_drafts, dirs_exist_ok=True)
            has_drafts = any(dest_drafts.iterdir())

        schema_version = _latest_schema_version(db_copy)
        manifest = {
            "plugin_id": "sysforge",
            "created_at": utc.format_storage(),
            "schema_version": schema_version,
            "contents": ["sysforge.db"]
            + (["config.json"] if has_config else [])
            + (["drafts/"] if has_drafts else []),
            "note": (
                "SysForge Business backup only. "
                "Not Odysseus /api/export (memories/presets/skills/host settings)."
            ),
        }
        (tmp_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_root / "manifest.json", "manifest.json")
            zf.write(db_copy, "sysforge.db")
            if has_config:
                zf.write(tmp_root / "config.json", "config.json")
            if has_drafts:
                for path in (tmp_root / "drafts").rglob("*"):
                    if path.is_file():
                        arc = path.relative_to(tmp_root).as_posix()
                        zf.write(path, arc)

        info = BackupInfo(
            id=backup_id,
            filename=zip_name,
            size_bytes=zip_path.stat().st_size,
            created_at=_created_at_iso(zip_path),
            has_config=has_config,
            has_drafts=has_drafts,
            kind="zip",
        )
        return BackupResult(
            success=True,
            message=f"Business backup created: {zip_name}",
            backup=info,
        )
    except Exception as exc:
        logger.exception("create_backup failed")
        if zip_path.is_file():
            try:
                zip_path.unlink()
            except OSError:
                pass
        return BackupResult(success=False, message=str(exc))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def list_backups() -> list[BackupInfo]:
    items: list[BackupInfo] = []
    for path in sorted(backups_dir().iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        name = path.name
        if not (_BACKUP_NAME_RE.match(name) or name.endswith((".zip", ".db"))):
            continue
        if not name.startswith("sysforge-backup-"):
            continue
        if name.endswith("-config.json"):
            continue
        kind = "zip" if name.lower().endswith(".zip") else "db"
        backup_id = _backup_id_from_filename(name)
        has_config = False
        has_drafts = False
        if kind == "db":
            has_config = (backups_dir() / f"{backup_id}-config.json").is_file()
            has_drafts = (backups_dir() / f"{backup_id}-drafts").is_dir()
        elif kind == "zip":
            has_config, has_drafts = _zip_contents_flags(path)
        items.append(
            BackupInfo(
                id=backup_id,
                filename=name,
                size_bytes=path.stat().st_size,
                created_at=_created_at_iso(path),
                has_config=has_config,
                has_drafts=has_drafts,
                kind=kind,
            )
        )
    return items


def find_backup_file(backup_id: str) -> Path | None:
    """Resolve backup_id to a file under backups/ (prefer .zip)."""
    safe = Path(backup_id).name
    if ".." in safe or "/" in safe or "\\" in safe:
        return None
    zip_path = backups_dir() / f"{safe}.zip"
    db_path = backups_dir() / f"{safe}.db"
    if zip_path.is_file():
        return zip_path
    if db_path.is_file():
        return db_path
    # Allow passing full filename as id
    direct = backups_dir() / safe
    if direct.is_file() and safe.startswith("sysforge-backup-"):
        return direct
    return None


def cleanup_old_backups(retention_days: int | None = None) -> int:
    days = retention_days
    if days is None:
        days = load_backup_schedule().retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))
    removed = 0
    for path in backups_dir().iterdir():
        if not path.is_file():
            continue
        if not path.name.startswith("sysforge-backup-"):
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def maybe_run_scheduled_backup() -> BackupResult | None:
    """Lazy scheduler: if enabled and due, create backup + retention cleanup.

    Prefer this over a long-lived asyncio timer so Docker sleep / single-worker
    hosts stay reliable. Cron can also hit ``POST /backup/create``.
    """
    schedule = load_backup_schedule()
    if not schedule.schedule_enabled:
        return None
    if schedule.last_run_at:
        try:
            last = utc.parse_storage(schedule.last_run_at)
        except ValueError:
            last = None
        if last is not None:
            due = last + timedelta(days=schedule.schedule_interval_days)
            if utc.utc_now() < due:
                return None
    result = create_backup(include_drafts=schedule.include_drafts)
    if result.success:
        save_backup_schedule({"last_run_at": utc.format_storage()})
        cleanup_old_backups(schedule.retention_days)
    return result


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------


def restore_backup(
    source: Path | str,
    *,
    restore_config: bool = False,
) -> RestoreResult:
    """Validate → safety backup → replace live DB → rebuild client search."""
    src = Path(source)
    if not src.is_file():
        return RestoreResult(success=False, message="Backup file not found.")

    suffix = src.suffix.lower()
    if suffix == ".sql":
        return RestoreResult(success=False, message=SQL_IMPORT_REJECT_MESSAGE)

    tmp_extract: Path | None = None
    db_file: Path
    config_file: Path | None = None

    try:
        if suffix == ".zip":
            tmp_extract = Path(tempfile.mkdtemp(prefix="sysforge-restore-"))
            db_file, config_file = _extract_zip_safe(src, tmp_extract)
        elif suffix == ".db":
            db_file = src
            sibling = src.with_name(src.stem + "-config.json")
            if sibling.is_file():
                config_file = sibling
        else:
            return RestoreResult(
                success=False,
                message="Unsupported backup type. Use a .zip or .db Business backup.",
            )

        if not validate_database_file(db_file):
            return RestoreResult(
                success=False,
                message="Backup file failed integrity check. Restore aborted.",
            )

        safety = create_backup(include_drafts=False)
        if not safety.success or not safety.backup:
            return RestoreResult(
                success=False,
                message=f"Could not create safety backup before restore: {safety.message}",
            )

        live = db_connection.db_path()
        checkpoint_database(live)
        # Replace live DB via temp + os.replace for atomicity
        dest_tmp = live.with_suffix(".restore-tmp")
        try:
            shutil.copy2(db_file, dest_tmp)
            os.replace(dest_tmp, live)
        finally:
            if dest_tmp.is_file():
                try:
                    dest_tmp.unlink()
                except OSError:
                    pass

        # Drop WAL/SHM sidecars that may reference pre-restore state
        for side in (live.with_suffix(".db-wal"), live.with_suffix(".db-shm")):
            # live is sysforge.db → sidecars are sysforge.db-wal
            pass
        for side_name in (f"{live.name}-wal", f"{live.name}-shm"):
            side_path = live.parent / side_name
            if side_path.is_file():
                try:
                    side_path.unlink()
                except OSError:
                    pass

        if restore_config and config_file and config_file.is_file():
            shutil.copy2(config_file, plugin_config.config_path())

        search_rebuilt = False
        try:
            rebuild_all_search(reason="db_restore")
            search_rebuilt = True
        except Exception as exc:
            logger.exception("Restore committed but search rebuild failed")
            return RestoreResult(
                success=False,
                message=(
                    "Database was restored, but search indexes could not be refreshed. "
                    "Run Rebuild search or restore again. "
                    f"({exc})"
                ),
                safety_backup_id=safety.backup.id,
                search_rebuilt=False,
            )

        return RestoreResult(
            success=True,
            message="Business database restored. Reload the Business panel to see changes.",
            safety_backup_id=safety.backup.id,
            search_rebuilt=search_rebuilt,
        )
    except BackupError as exc:
        return RestoreResult(success=False, message=str(exc))
    except Exception as exc:
        logger.exception("restore_backup failed")
        return RestoreResult(success=False, message=str(exc))
    finally:
        if tmp_extract is not None:
            shutil.rmtree(tmp_extract, ignore_errors=True)


def _extract_zip_safe(zip_path: Path, dest: Path) -> tuple[Path, Path | None]:
    dest = dest.resolve()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/"):
                raise BackupError("Archive contains unsafe paths.")
            target = (dest / name).resolve()
            if not str(target).startswith(str(dest)):
                raise BackupError("Archive path escapes extract directory.")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)

    db_file = dest / "sysforge.db"
    if not db_file.is_file():
        # Allow zip that only contains a lone .db at root
        dbs = list(dest.glob("*.db"))
        if len(dbs) == 1:
            db_file = dbs[0]
        else:
            raise BackupError("ZIP backup missing sysforge.db.")
    config_file = dest / "config.json"
    return db_file, config_file if config_file.is_file() else None


# ---------------------------------------------------------------------------
# JSON export / import
# ---------------------------------------------------------------------------


def export_to_json() -> dict[str, Any]:
    """Build SysForgeExportData v1.0 from the live Business database.

    Includes payments, invoice document metadata, and ``mergedIntoClientId``.
    Soft-deleted merge losers (``MergedIntoClientId`` set) are exported so
    merge links survive JSON round-trip. ZIP backups already carry full DB.
    """
    live = db_connection.db_path()
    if not live.is_file():
        raise BackupError("Business database not found.")
    if not validate_database_file(live):
        raise BackupError("Database failed integrity check. Export aborted.")

    checkpoint_database(live)
    conn = db_connection.connect()
    try:
        clients = [
            _row_client_export(dict(r))
            for r in conn.execute(
                """
                SELECT * FROM Clients
                WHERE IsDeleted = 0 OR MergedIntoClientId IS NOT NULL
                ORDER BY Id
                """
            )
        ]
        parts = [
            _row_part_export(dict(r))
            for r in conn.execute("SELECT * FROM Parts ORDER BY Id")
        ]
        invoices = [
            _row_invoice_export(dict(r))
            for r in conn.execute("SELECT * FROM Invoices ORDER BY Id")
        ]
        items = [
            _row_item_export(dict(r))
            for r in conn.execute("SELECT * FROM InvoiceItems ORDER BY Id")
        ]
        payments = [
            _row_payment_export(dict(r))
            for r in conn.execute("SELECT * FROM Payments ORDER BY Id")
        ]
        documents = [
            _row_invoice_document_export(dict(r))
            for r in conn.execute("SELECT * FROM InvoiceDocuments ORDER BY Id")
        ]
    finally:
        conn.close()

    return {
        "exportVersion": EXPORT_VERSION,
        "exportDate": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "clients": clients,
        "invoices": invoices,
        "invoiceItems": items,
        "parts": parts,
        "payments": payments,
        "invoiceDocuments": documents,
        "settings": _export_settings_payload(),
    }


def import_from_json(
    data: dict[str, Any] | str | bytes,
    options: ImportOptions | None = None,
) -> ImportResult:
    """Transactional JSON import + BUG-018 search rebuild when clients in scope."""
    opts = options or ImportOptions()
    if isinstance(data, (str, bytes)):
        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise BackupError("Invalid JSON") from exc
    else:
        payload = data

    if not isinstance(payload, dict):
        raise BackupError("Invalid export file format.")

    version = str(payload.get("exportVersion") or payload.get("export_version") or "")
    if version != EXPORT_VERSION:
        raise UnsupportedExportVersion(
            f"Unsupported export version '{version}'. Expected {EXPORT_VERSION}."
        )

    result = ImportResult()
    conn = db_connection.connect()
    try:
        conn.execute("BEGIN")
        try:
            if opts.import_clients:
                for client in payload.get("clients") or []:
                    _import_one_client(conn, client, opts, result)
                # Second pass: merge links (survivor must exist first).
                for client in payload.get("clients") or []:
                    _apply_merged_into(conn, client)

            if opts.import_parts:
                for part in payload.get("parts") or []:
                    _import_one_part(conn, part, opts, result)

            if opts.import_invoices:
                for invoice in payload.get("invoices") or []:
                    _import_one_invoice(conn, invoice, opts, result)

            if opts.import_invoice_items:
                for item in payload.get("invoiceItems") or payload.get("invoice_items") or []:
                    _import_one_item(conn, item, opts, result)

            # Optional v1.0 extensions (absent in older fixtures → no-op).
            if opts.import_invoices:
                for payment in payload.get("payments") or []:
                    _import_one_payment(conn, payment, opts, result)
                for doc in (
                    payload.get("invoiceDocuments")
                    or payload.get("invoice_documents")
                    or []
                ):
                    _import_one_invoice_document(conn, doc, opts, result)

            if opts.import_settings and payload.get("settings") is not None:
                _import_settings(payload["settings"])
                result.settings_imported = True

            conn.commit()
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()

    # BUG-018: rebuild whenever clients/parts were in import scope (ignore counts).
    if opts.import_clients or opts.import_parts:
        try:
            rebuild_all_search(
                reason=(
                    f"json_import clients={result.clients_imported} "
                    f"parts={getattr(result, 'parts_imported', 0)}"
                )
            )
            result.search_rebuilt = True
        except Exception as exc:
            logger.exception("JSON import committed but search rebuild failed")
            result.success = False
            result.message = (
                "Data was saved, but search indexes could not be refreshed. "
                "Import the same JSON file again to retry search sync, "
                f"or use Rebuild search. ({exc})"
            )
            return result

    result.success = True
    result.message = "Import completed successfully."
    return result


# ---------------------------------------------------------------------------
# Row helpers
# ---------------------------------------------------------------------------


def _get(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
        # PascalCase / camelCase
        lower = {str(k).lower(): v for k, v in row.items()}
        if key.lower() in lower and lower[key.lower()] is not None:
            return lower[key.lower()]
    return default


def _as_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return 1 if value else 0
    try:
        return 1 if int(value) else 0
    except (TypeError, ValueError):
        return default


def _parse_ts(value: Any) -> str:
    if value is None or value == "":
        return utc.format_storage()
    text = str(value).strip()
    if "T" in text:
        # ISO → storage
        raw = text.replace("Z", "").replace("z", "")
        try:
            if "." in raw:
                raw = raw.split(".", 1)[0]
            dt = datetime.fromisoformat(raw)
            return utc.format_storage(dt)
        except ValueError:
            pass
    try:
        return utc.format_storage(utc.parse_storage(text))
    except ValueError:
        return utc.format_storage()


def _row_client_export(row: dict[str, Any]) -> dict[str, Any]:
    merged = row.get("MergedIntoClientId")
    return {
        "id": row["Id"],
        "firstName": row.get("FirstName"),
        "lastName": row.get("LastName"),
        "nickname": row.get("Nickname"),
        "phoneNumber": row.get("PhoneNumber"),
        "email": row.get("Email"),
        "address": row.get("Address"),
        "company": row.get("Company"),
        "associates": row.get("Associates"),
        "referredBy": row.get("ReferredBy"),
        "notes": row.get("Notes"),
        "isIncomplete": bool(row.get("IsIncomplete")),
        "isDeleted": bool(row.get("IsDeleted")),
        "mergedIntoClientId": int(merged) if merged is not None else None,
        "dateAdded": _iso_from_storage(row.get("DateAdded")),
        "lastUpdated": _iso_from_storage(row.get("LastUpdated")),
    }


def _row_part_export(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["Id"],
        "name": row.get("Name"),
        "basePriceCents": row.get("BasePriceCents", 0),
        "description": row.get("Description"),
        "sku": row.get("SKU"),
        "compatibleDevices": row.get("CompatibleDevices"),
        "tags": row.get("Tags"),
        "hasWarranty": bool(row.get("HasWarranty")),
        "supplierId": row.get("SupplierId"),
        "dateAdded": _iso_from_storage(row.get("DateAdded")),
        "lastUpdated": _iso_from_storage(row.get("LastUpdated")),
        "isPlaceholder": bool(row.get("IsPlaceholder")),
    }


def _row_invoice_export(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["Id"],
        "clientId": row.get("ClientId"),
        "clientInfo": row.get("ClientInfo"),
        "name": row.get("Name"),
        "dateCreated": _iso_from_storage(row.get("DateCreated")),
        "lastEditedAt": _iso_from_storage(row.get("LastEditedAt")),
        "partsSubtotalCents": row.get("PartsSubtotalCents", 0),
        "laborCostCents": row.get("LaborCostCents", 0),
        "shippingCostCents": row.get("ShippingCostCents", 0),
        "taxAmountCents": row.get("TaxAmountCents", 0),
        "finalTotalCents": row.get("FinalTotalCents", 0),
        "includeTax": bool(row.get("IncludeTax", 1)),
        "includeShipping": bool(row.get("IncludeShipping", 1)),
        "taxRateBasisPoints": row.get("TaxRateBasisPoints", 775),
        "shippingRateCents": row.get("ShippingRateCents", 0),
        "status": row.get("Status") or "Estimate",
        "isFinalized": bool(row.get("IsFinalized")),
        "sentAt": _iso_from_storage(row.get("SentAt")) if row.get("SentAt") else None,
    }


def _row_item_export(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["Id"],
        "invoiceId": row.get("InvoiceId"),
        "partId": row.get("PartId"),
        "supplierId": row.get("SupplierId"),
        "partName": row.get("PartName"),
        "sku": row.get("SKU"),
        "quantityMilliunits": row.get("QuantityMilliunits", 1000),
        "unitPriceCents": row.get("UnitPriceCents", 0),
        "lineTotalCents": row.get("LineTotalCents", 0),
        "discountType": row.get("DiscountType") or "None",
        "discountValue": row.get("DiscountValue", 0),
        "isTaxable": bool(row.get("IsTaxable", 1)),
        "sortOrder": row.get("SortOrder", 0),
        "itemType": row.get("ItemType") or "Part",
    }


def _row_payment_export(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["Id"],
        "invoiceId": row.get("InvoiceId"),
        "amountCents": row.get("AmountCents", 0),
        "method": row.get("Method") or "Other",
        "reference": row.get("Reference"),
        "receivedAt": _iso_from_storage(row.get("ReceivedAt")),
        "notes": row.get("Notes"),
        "isVoided": bool(row.get("IsVoided")),
        "voidedAt": _iso_from_storage(row.get("VoidedAt")) if row.get("VoidedAt") else None,
        "voidReason": row.get("VoidReason"),
    }


def _row_invoice_document_export(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["Id"],
        "invoiceId": row.get("InvoiceId"),
        "kind": row.get("Kind") or "pdf",
        "fileName": row.get("FileName"),
        "mimeType": row.get("MimeType") or "application/pdf",
        "sizeBytes": row.get("SizeBytes", 0),
        "storedRelPath": row.get("StoredRelPath"),
        "sha256": row.get("Sha256"),
        "createdAt": _iso_from_storage(row.get("CreatedAt")),
    }


def _iso_from_storage(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        dt = utc.parse_storage(str(value))
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return str(value)


def _import_one_client(
    conn: sqlite3.Connection,
    raw: dict[str, Any],
    opts: ImportOptions,
    result: ImportResult,
) -> None:
    cid = _as_int(_get(raw, "id", "Id"), 0)
    if cid <= 0:
        return
    existing = conn.execute("SELECT Id FROM Clients WHERE Id = ?", (cid,)).fetchone()
    phone = _get(raw, "phoneNumber", "PhoneNumber")
    phone_norm = normalize_phone(phone) or None
    params = {
        "Id": cid,
        "FirstName": _get(raw, "firstName", "FirstName"),
        "LastName": _get(raw, "lastName", "LastName"),
        "Nickname": _get(raw, "nickname", "Nickname"),
        "PhoneNumber": phone,
        "PhoneNorm": phone_norm,
        "Email": _get(raw, "email", "Email"),
        "Address": _get(raw, "address", "Address"),
        "Company": _get(raw, "company", "Company"),
        "Associates": _get(raw, "associates", "Associates"),
        "ReferredBy": _get(raw, "referredBy", "ReferredBy"),
        "Notes": _get(raw, "notes", "Notes"),
        "IsIncomplete": _as_bool_int(_get(raw, "isIncomplete", "IsIncomplete"), 0),
        "IsDeleted": _as_bool_int(_get(raw, "isDeleted", "IsDeleted"), 0),
        "DateAdded": _parse_ts(_get(raw, "dateAdded", "DateAdded")),
        "LastUpdated": _parse_ts(_get(raw, "lastUpdated", "LastUpdated")),
    }
    if existing:
        if opts.conflict == "skip":
            result.clients_skipped += 1
            return
        conn.execute(
            """
            UPDATE Clients SET
              FirstName=:FirstName, LastName=:LastName, Nickname=:Nickname,
              PhoneNumber=:PhoneNumber, PhoneNorm=:PhoneNorm, Email=:Email,
              Address=:Address, Company=:Company, Associates=:Associates,
              ReferredBy=:ReferredBy, Notes=:Notes, IsIncomplete=:IsIncomplete,
              IsDeleted=:IsDeleted, DateAdded=:DateAdded, LastUpdated=:LastUpdated
            WHERE Id=:Id
            """,
            params,
        )
        result.clients_imported += 1
        return
    conn.execute(
        """
        INSERT INTO Clients (
          Id, FirstName, LastName, Nickname, PhoneNumber, PhoneNorm, Email,
          Address, Company, Associates, ReferredBy, Notes, IsIncomplete,
          IsDeleted, DateAdded, LastUpdated
        ) VALUES (
          :Id, :FirstName, :LastName, :Nickname, :PhoneNumber, :PhoneNorm, :Email,
          :Address, :Company, :Associates, :ReferredBy, :Notes, :IsIncomplete,
          :IsDeleted, :DateAdded, :LastUpdated
        )
        """,
        params,
    )
    result.clients_imported += 1


def _apply_merged_into(conn: sqlite3.Connection, raw: dict[str, Any]) -> None:
    cid = _as_int(_get(raw, "id", "Id"), 0)
    merged = _optional_int(_get(raw, "mergedIntoClientId", "MergedIntoClientId"))
    if cid <= 0:
        return
    conn.execute(
        "UPDATE Clients SET MergedIntoClientId = ? WHERE Id = ?",
        (merged, cid),
    )


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _import_one_payment(
    conn: sqlite3.Connection,
    raw: dict[str, Any],
    opts: ImportOptions,
    result: ImportResult,
) -> None:
    pid = _as_int(_get(raw, "id", "Id"), 0)
    invoice_id = _as_int(_get(raw, "invoiceId", "InvoiceId"), 0)
    if pid <= 0 or invoice_id <= 0:
        return
    existing = conn.execute("SELECT Id FROM Payments WHERE Id = ?", (pid,)).fetchone()
    if existing and opts.conflict == "skip":
        return
    params = {
        "Id": pid,
        "InvoiceId": invoice_id,
        "AmountCents": _as_int(_get(raw, "amountCents", "AmountCents"), 0),
        "Method": str(_get(raw, "method", "Method") or "Other"),
        "Reference": _get(raw, "reference", "Reference"),
        "ReceivedAt": _parse_ts(_get(raw, "receivedAt", "ReceivedAt")),
        "Notes": _get(raw, "notes", "Notes"),
        "IsVoided": _as_bool_int(_get(raw, "isVoided", "IsVoided"), 0),
        "VoidedAt": (
            _parse_ts(_get(raw, "voidedAt", "VoidedAt"))
            if _get(raw, "voidedAt", "VoidedAt")
            else None
        ),
        "VoidReason": _get(raw, "voidReason", "VoidReason"),
    }
    if existing:
        conn.execute(
            """
            UPDATE Payments SET
              InvoiceId=:InvoiceId, AmountCents=:AmountCents, Method=:Method,
              Reference=:Reference, ReceivedAt=:ReceivedAt, Notes=:Notes,
              IsVoided=:IsVoided, VoidedAt=:VoidedAt, VoidReason=:VoidReason
            WHERE Id=:Id
            """,
            params,
        )
    else:
        conn.execute(
            """
            INSERT INTO Payments (
              Id, InvoiceId, AmountCents, Method, Reference, ReceivedAt, Notes,
              IsVoided, VoidedAt, VoidReason
            ) VALUES (
              :Id, :InvoiceId, :AmountCents, :Method, :Reference, :ReceivedAt, :Notes,
              :IsVoided, :VoidedAt, :VoidReason
            )
            """,
            params,
        )
    result.payments_imported += 1


def _import_one_invoice_document(
    conn: sqlite3.Connection,
    raw: dict[str, Any],
    opts: ImportOptions,
    result: ImportResult,
) -> None:
    did = _as_int(_get(raw, "id", "Id"), 0)
    invoice_id = _as_int(_get(raw, "invoiceId", "InvoiceId"), 0)
    if did <= 0 or invoice_id <= 0:
        return
    existing = conn.execute(
        "SELECT Id FROM InvoiceDocuments WHERE Id = ?", (did,)
    ).fetchone()
    if existing and opts.conflict == "skip":
        return
    params = {
        "Id": did,
        "InvoiceId": invoice_id,
        "Kind": str(_get(raw, "kind", "Kind") or "pdf"),
        "FileName": _get(raw, "fileName", "FileName") or "invoice.pdf",
        "MimeType": _get(raw, "mimeType", "MimeType") or "application/pdf",
        "SizeBytes": _as_int(_get(raw, "sizeBytes", "SizeBytes"), 0),
        "StoredRelPath": _get(raw, "storedRelPath", "StoredRelPath") or "",
        "Sha256": _get(raw, "sha256", "Sha256"),
        "CreatedAt": _parse_ts(_get(raw, "createdAt", "CreatedAt")),
    }
    if existing:
        conn.execute(
            """
            UPDATE InvoiceDocuments SET
              InvoiceId=:InvoiceId, Kind=:Kind, FileName=:FileName,
              MimeType=:MimeType, SizeBytes=:SizeBytes,
              StoredRelPath=:StoredRelPath, Sha256=:Sha256, CreatedAt=:CreatedAt
            WHERE Id=:Id
            """,
            params,
        )
    else:
        conn.execute(
            """
            INSERT INTO InvoiceDocuments (
              Id, InvoiceId, Kind, FileName, MimeType, SizeBytes,
              StoredRelPath, Sha256, CreatedAt
            ) VALUES (
              :Id, :InvoiceId, :Kind, :FileName, :MimeType, :SizeBytes,
              :StoredRelPath, :Sha256, :CreatedAt
            )
            """,
            params,
        )
    result.invoice_documents_imported += 1


def _import_one_part(
    conn: sqlite3.Connection,
    raw: dict[str, Any],
    opts: ImportOptions,
    result: ImportResult,
) -> None:
    pid = _as_int(_get(raw, "id", "Id"), 0)
    if pid <= 0:
        return
    existing = conn.execute("SELECT Id FROM Parts WHERE Id = ?", (pid,)).fetchone()
    params = {
        "Id": pid,
        "Name": _get(raw, "name", "Name") or "Part",
        "BasePriceCents": _as_int(_get(raw, "basePriceCents", "BasePriceCents"), 0),
        "Description": _get(raw, "description", "Description"),
        "SKU": _get(raw, "sku", "SKU"),
        "CompatibleDevices": _get(raw, "compatibleDevices", "CompatibleDevices"),
        "Tags": _get(raw, "tags", "Tags"),
        "HasWarranty": _as_bool_int(_get(raw, "hasWarranty", "HasWarranty"), 0),
        "SupplierId": _get(raw, "supplierId", "SupplierId"),
        "DateAdded": _parse_ts(_get(raw, "dateAdded", "DateAdded")),
        "LastUpdated": _parse_ts(_get(raw, "lastUpdated", "LastUpdated")),
        "IsPlaceholder": _as_bool_int(_get(raw, "isPlaceholder", "IsPlaceholder"), 0),
    }
    if existing:
        if opts.conflict == "skip":
            result.parts_skipped += 1
            return
        conn.execute(
            """
            UPDATE Parts SET
              Name=:Name, BasePriceCents=:BasePriceCents, Description=:Description,
              SKU=:SKU, CompatibleDevices=:CompatibleDevices, Tags=:Tags,
              HasWarranty=:HasWarranty, SupplierId=:SupplierId,
              DateAdded=:DateAdded, LastUpdated=:LastUpdated,
              IsPlaceholder=:IsPlaceholder
            WHERE Id=:Id
            """,
            params,
        )
        result.parts_imported += 1
        return
    conn.execute(
        """
        INSERT INTO Parts (
          Id, Name, BasePriceCents, Description, SKU, CompatibleDevices, Tags,
          HasWarranty, SupplierId, DateAdded, LastUpdated, IsPlaceholder
        ) VALUES (
          :Id, :Name, :BasePriceCents, :Description, :SKU, :CompatibleDevices, :Tags,
          :HasWarranty, :SupplierId, :DateAdded, :LastUpdated, :IsPlaceholder
        )
        """,
        params,
    )
    result.parts_imported += 1


def _import_one_invoice(
    conn: sqlite3.Connection,
    raw: dict[str, Any],
    opts: ImportOptions,
    result: ImportResult,
) -> None:
    iid = _as_int(_get(raw, "id", "Id"), 0)
    if iid <= 0:
        return
    existing = conn.execute("SELECT Id FROM Invoices WHERE Id = ?", (iid,)).fetchone()
    params = {
        "Id": iid,
        "ClientId": _get(raw, "clientId", "ClientId"),
        "ClientInfo": _get(raw, "clientInfo", "ClientInfo"),
        "Name": _get(raw, "name", "Name"),
        "DateCreated": _parse_ts(_get(raw, "dateCreated", "DateCreated")),
        "LastEditedAt": _parse_ts(
            _get(raw, "lastEditedAt", "LastEditedAt")
            or _get(raw, "dateCreated", "DateCreated")
        ),
        "PartsSubtotalCents": _as_int(
            _get(raw, "partsSubtotalCents", "PartsSubtotalCents"), 0
        ),
        "LaborCostCents": _as_int(_get(raw, "laborCostCents", "LaborCostCents"), 0),
        "ShippingCostCents": _as_int(
            _get(raw, "shippingCostCents", "ShippingCostCents"), 0
        ),
        "TaxAmountCents": _as_int(_get(raw, "taxAmountCents", "TaxAmountCents"), 0),
        "FinalTotalCents": _as_int(_get(raw, "finalTotalCents", "FinalTotalCents"), 0),
        "IncludeTax": _as_bool_int(_get(raw, "includeTax", "IncludeTax"), 1),
        "IncludeShipping": _as_bool_int(
            _get(raw, "includeShipping", "IncludeShipping"), 1
        ),
        "TaxRateBasisPoints": _as_int(
            _get(raw, "taxRateBasisPoints", "TaxRateBasisPoints"), 775
        ),
        "ShippingRateCents": _as_int(
            _get(raw, "shippingRateCents", "ShippingRateCents"), 0
        ),
        "Status": map_status(_get(raw, "status", "Status")),
        "IsFinalized": _as_bool_int(_get(raw, "isFinalized", "IsFinalized"), 0),
        "SentAt": (
            _parse_ts(_get(raw, "sentAt", "SentAt"))
            if _get(raw, "sentAt", "SentAt")
            else None
        ),
    }
    if existing:
        if opts.conflict == "skip":
            result.invoices_skipped += 1
            return
        conn.execute(
            """
            UPDATE Invoices SET
              ClientId=:ClientId, ClientInfo=:ClientInfo, Name=:Name,
              DateCreated=:DateCreated, LastEditedAt=:LastEditedAt,
              PartsSubtotalCents=:PartsSubtotalCents, LaborCostCents=:LaborCostCents,
              ShippingCostCents=:ShippingCostCents, TaxAmountCents=:TaxAmountCents,
              FinalTotalCents=:FinalTotalCents, IncludeTax=:IncludeTax,
              IncludeShipping=:IncludeShipping, TaxRateBasisPoints=:TaxRateBasisPoints,
              ShippingRateCents=:ShippingRateCents, Status=:Status,
              IsFinalized=:IsFinalized, SentAt=:SentAt
            WHERE Id=:Id
            """,
            params,
        )
        result.invoices_imported += 1
        return
    conn.execute(
        """
        INSERT INTO Invoices (
          Id, ClientId, ClientInfo, Name, DateCreated, LastEditedAt,
          PartsSubtotalCents, LaborCostCents, ShippingCostCents, TaxAmountCents,
          FinalTotalCents, IncludeTax, IncludeShipping, TaxRateBasisPoints,
          ShippingRateCents, Status, IsFinalized, SentAt
        ) VALUES (
          :Id, :ClientId, :ClientInfo, :Name, :DateCreated, :LastEditedAt,
          :PartsSubtotalCents, :LaborCostCents, :ShippingCostCents, :TaxAmountCents,
          :FinalTotalCents, :IncludeTax, :IncludeShipping, :TaxRateBasisPoints,
          :ShippingRateCents, :Status, :IsFinalized, :SentAt
        )
        """,
        params,
    )
    result.invoices_imported += 1


def _import_one_item(
    conn: sqlite3.Connection,
    raw: dict[str, Any],
    opts: ImportOptions,
    result: ImportResult,
) -> None:
    item_id = _as_int(_get(raw, "id", "Id"), 0)
    if item_id <= 0:
        return
    existing = conn.execute(
        "SELECT Id FROM InvoiceItems WHERE Id = ?", (item_id,)
    ).fetchone()
    if existing and opts.conflict == "skip":
        return
    params = {
        "Id": item_id,
        "InvoiceId": _as_int(_get(raw, "invoiceId", "InvoiceId"), 0),
        "PartId": _get(raw, "partId", "PartId"),
        "SupplierId": _get(raw, "supplierId", "SupplierId"),
        "PartName": _get(raw, "partName", "PartName") or "Item",
        "SKU": _get(raw, "sku", "SKU"),
        "QuantityMilliunits": _as_int(
            _get(raw, "quantityMilliunits", "QuantityMilliunits"), 1000
        ),
        "UnitPriceCents": _as_int(_get(raw, "unitPriceCents", "UnitPriceCents"), 0),
        "LineTotalCents": _as_int(_get(raw, "lineTotalCents", "LineTotalCents"), 0),
        "DiscountType": map_discount_type(_get(raw, "discountType", "DiscountType")),
        "DiscountValue": _as_int(_get(raw, "discountValue", "DiscountValue"), 0),
        "IsTaxable": _as_bool_int(_get(raw, "isTaxable", "IsTaxable"), 1),
        "SortOrder": _as_int(_get(raw, "sortOrder", "SortOrder"), 0),
        "ItemType": map_item_type(_get(raw, "itemType", "ItemType")),
    }
    if existing:
        conn.execute(
            """
            UPDATE InvoiceItems SET
              InvoiceId=:InvoiceId, PartId=:PartId, SupplierId=:SupplierId,
              PartName=:PartName, SKU=:SKU, QuantityMilliunits=:QuantityMilliunits,
              UnitPriceCents=:UnitPriceCents, LineTotalCents=:LineTotalCents,
              DiscountType=:DiscountType, DiscountValue=:DiscountValue,
              IsTaxable=:IsTaxable, SortOrder=:SortOrder, ItemType=:ItemType
            WHERE Id=:Id
            """,
            params,
        )
    else:
        conn.execute(
            """
            INSERT INTO InvoiceItems (
              Id, InvoiceId, PartId, SupplierId, PartName, SKU,
              QuantityMilliunits, UnitPriceCents, LineTotalCents,
              DiscountType, DiscountValue, IsTaxable, SortOrder, ItemType
            ) VALUES (
              :Id, :InvoiceId, :PartId, :SupplierId, :PartName, :SKU,
              :QuantityMilliunits, :UnitPriceCents, :LineTotalCents,
              :DiscountType, :DiscountValue, :IsTaxable, :SortOrder, :ItemType
            )
            """,
            params,
        )
    result.invoice_items_imported += 1


def _export_settings_payload() -> dict[str, Any]:
    cfg = plugin_config.load_config()
    schedule = load_backup_schedule()
    bps = int(cfg.get("tax_rate_bps", 775))
    return {
        "version": 1,
        "defaults": {
            "taxRate": float(money.from_basis_points(bps)),
            "includeTax": True,
            "includeShipping": True,
        },
        "autosave": {
            "enabled": bool(cfg.get("autosave_drafts", True)),
            "intervalSeconds": int(cfg.get("autosave_interval_seconds", 60)),
        },
        "currency": cfg.get("currency", "USD"),
        "drafts": cfg.get("drafts") if isinstance(cfg.get("drafts"), dict) else {},
        "backup": schedule.to_dict(),
    }


def _import_settings(settings: Any) -> None:
    if not isinstance(settings, dict):
        return
    partial: dict[str, Any] = {}
    defaults = settings.get("defaults") if isinstance(settings.get("defaults"), dict) else {}
    if "taxRate" in defaults and defaults["taxRate"] is not None:
        try:
            partial["tax_rate_bps"] = money.to_basis_points(defaults["taxRate"])
        except Exception:
            pass
    if "tax_rate_bps" in settings:
        partial["tax_rate_bps"] = int(settings["tax_rate_bps"])
    if settings.get("currency"):
        partial["currency"] = str(settings["currency"]).upper()
    autosave = settings.get("autosave") if isinstance(settings.get("autosave"), dict) else {}
    if "enabled" in autosave:
        partial["autosave_drafts"] = bool(autosave["enabled"])
    if "intervalSeconds" in autosave:
        partial["autosave_interval_seconds"] = int(autosave["intervalSeconds"])
    if partial:
        try:
            plugin_config.save_config(partial)
        except plugin_config.ConfigValidationError:
            logger.warning("Skipped invalid settings fields during import")

    backup = settings.get("backup") if isinstance(settings.get("backup"), dict) else {}
    if backup:
        mapped = {}
        if "scheduleEnabled" in backup or "schedule_enabled" in backup:
            mapped["schedule_enabled"] = bool(
                backup.get("schedule_enabled", backup.get("scheduleEnabled"))
            )
        if "scheduleIntervalDays" in backup or "schedule_interval_days" in backup:
            mapped["schedule_interval_days"] = int(
                backup.get("schedule_interval_days", backup.get("scheduleIntervalDays"))
            )
        if "retentionDays" in backup or "retention_days" in backup:
            mapped["retention_days"] = int(
                backup.get("retention_days", backup.get("retentionDays"))
            )
        if "includeDrafts" in backup or "include_drafts" in backup:
            mapped["include_drafts"] = bool(
                backup.get("include_drafts", backup.get("includeDrafts"))
            )
        if mapped:
            save_backup_schedule(mapped)


def _latest_schema_version(db_path: Path) -> int | None:
    try:
        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT MAX(Id) FROM SchemaVersion"
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def _created_at_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _zip_contents_flags(path: Path) -> tuple[bool, bool]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = {n.replace("\\", "/") for n in zf.namelist()}
        has_config = "config.json" in names
        has_drafts = any(n.startswith("drafts/") for n in names)
        return has_config, has_drafts
    except zipfile.BadZipFile:
        return False, False
