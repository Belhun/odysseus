"""Business backup / restore / JSON import HTTP routes.

Mounted under ``/api/sysforge/backup/*``. Separate from Odysseus ``/api/export``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from integrations.sysforge import backup_service
from integrations.sysforge.backup_models import (
    SQL_IMPORT_REJECT_MESSAGE,
    ImportOptions,
)
from integrations.sysforge.backup_service import (
    BackupError,
    UnsupportedExportVersion,
)


class BackupCreateBody(BaseModel):
    include_drafts: bool | None = None


class BackupRestoreBody(BaseModel):
    backup_id: str
    restore_config: bool = False


class BackupScheduleBody(BaseModel):
    schedule_enabled: bool | None = None
    schedule_interval_days: int | None = None
    retention_days: int | None = None
    include_drafts: bool | None = None


def register_backup_routes(router: APIRouter) -> None:
    """Attach backup endpoints to the SysForge API router."""

    @router.get("/backup/list")
    def backup_list():
        backup_service.maybe_run_scheduled_backup()
        return {
            "ok": True,
            "backups": [b.to_dict() for b in backup_service.list_backups()],
        }

    @router.post("/backup/create")
    def backup_create(body: BackupCreateBody | None = None):
        include = None if body is None else body.include_drafts
        result = backup_service.create_backup(include_drafts=include)
        if not result.success:
            raise HTTPException(400, result.message)
        return {
            "ok": True,
            "backup": result.backup.to_dict() if result.backup else None,
            "message": result.message,
        }

    @router.get("/backup/download/{backup_id}")
    def backup_download(backup_id: str):
        path = backup_service.find_backup_file(backup_id)
        if path is None:
            raise HTTPException(404, "Backup not found")
        media = (
            "application/zip"
            if path.suffix.lower() == ".zip"
            else "application/octet-stream"
        )
        data = path.read_bytes()
        return Response(
            content=data,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{path.name}"',
            },
        )

    @router.post("/backup/restore")
    async def backup_restore(
        body: BackupRestoreBody | None = None,
        file: UploadFile | None = File(None),
        restore_config: bool = Form(False),
        backup_id: str | None = Form(None),
    ):
        """Restore from ``backup_id`` JSON body or uploaded ``.zip`` / ``.db``."""
        if file is not None and file.filename:
            name = file.filename or ""
            lower = name.lower()
            if lower.endswith(".sql"):
                raise HTTPException(400, SQL_IMPORT_REJECT_MESSAGE)
            raw = await file.read()
            if not raw:
                raise HTTPException(400, "Empty upload")
            import tempfile
            from pathlib import Path

            suffix = ".zip" if lower.endswith(".zip") else ".db"
            if not (lower.endswith(".zip") or lower.endswith(".db")):
                raise HTTPException(
                    400,
                    "Unsupported file type. Use a Business .zip or .db backup "
                    "(SQL dump import is not supported).",
                )
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(raw)
                tmp_path = Path(tmp.name)
            try:
                result = backup_service.restore_backup(
                    tmp_path, restore_config=bool(restore_config)
                )
            finally:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
        else:
            bid = (body.backup_id if body else None) or backup_id
            if not bid:
                raise HTTPException(400, "Provide backup_id or upload a backup file")
            path = backup_service.find_backup_file(bid)
            if path is None:
                raise HTTPException(404, "Backup not found")
            cfg = bool(body.restore_config) if body else bool(restore_config)
            result = backup_service.restore_backup(path, restore_config=cfg)

        status = 200 if result.success else (500 if result.safety_backup_id else 400)
        return JSONResponse(
            status_code=status,
            content={
                "ok": result.success,
                "message": result.message,
                "safety_backup_id": result.safety_backup_id,
                "search_rebuilt": result.search_rebuilt,
            },
        )

    @router.get("/backup/export.json")
    def backup_export_json():
        try:
            payload = backup_service.export_to_json()
        except BackupError as exc:
            raise HTTPException(400, str(exc)) from exc
        content = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="sysforge-export.json"',
            },
        )

    @router.post("/backup/import.json")
    async def backup_import_json(
        file: UploadFile = File(...),
        import_clients: bool = Form(True),
        import_invoices: bool = Form(True),
        import_invoice_items: bool = Form(True),
        import_parts: bool = Form(True),
        import_settings: bool = Form(True),
        conflict: str = Form("skip"),
    ):
        name = (file.filename or "").lower()
        if name.endswith(".sql"):
            raise HTTPException(400, SQL_IMPORT_REJECT_MESSAGE)
        raw = await file.read()
        if not raw:
            raise HTTPException(400, "Empty upload")
        # Reject SQL content disguised as JSON
        stripped = raw.lstrip()[:40].lower()
        if stripped.startswith(b"pragma") or stripped.startswith(b"begin"):
            raise HTTPException(400, SQL_IMPORT_REJECT_MESSAGE)

        opts = ImportOptions.from_mapping(
            {
                "import_clients": import_clients,
                "import_invoices": import_invoices,
                "import_invoice_items": import_invoice_items,
                "import_parts": import_parts,
                "import_settings": import_settings,
                "conflict": conflict,
            }
        )
        try:
            result = backup_service.import_from_json(raw, opts)
        except UnsupportedExportVersion as exc:
            raise HTTPException(400, str(exc)) from exc
        except BackupError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            # FK / CHECK failures
            raise HTTPException(400, f"Import failed: {exc}") from exc

        body_out: dict[str, Any] = {
            "ok": result.success,
            "message": result.message,
            **result.to_dict(),
        }
        # Prefer ok at top; to_dict also has success
        status = 200 if result.success else 500
        return JSONResponse(status_code=status, content=body_out)

    @router.post("/backup/search/rebuild")
    def backup_search_rebuild():
        try:
            counts = backup_service.rebuild_all_search(reason="manual")
        except Exception as exc:
            raise HTTPException(500, f"Search rebuild failed: {exc}") from exc
        return {"ok": True, **counts}

    @router.get("/backup/schedule")
    def backup_schedule_get():
        return {"ok": True, **backup_service.load_backup_schedule().to_dict()}

    @router.put("/backup/schedule")
    def backup_schedule_put(body: BackupScheduleBody):
        partial = body.model_dump(exclude_unset=True)
        schedule = backup_service.save_backup_schedule(partial)
        # Kick if just enabled and due
        backup_service.maybe_run_scheduled_backup()
        return {"ok": True, **schedule.to_dict()}
