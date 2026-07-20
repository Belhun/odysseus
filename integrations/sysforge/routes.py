"""SysForge Business Management API — gated by plugin install state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from integrations.sysforge.config import (
    ConfigValidationError,
    load_config,
    save_config,
    save_drafts_retention,
    settings_response,
)
from integrations.sysforge.db.exceptions import ChecksumMismatchError, MigrationError
from integrations.sysforge.db.migration_runner import ensure_schema, schema_status
from integrations.sysforge.diagnostics import collect_diagnostics
from integrations.sysforge.drafts.models import list_item_dto
from integrations.sysforge.drafts.service import get_draft_service
from integrations.sysforge.services import parts as parts_service
from integrations.sysforge.services.parts import PartValidationError
from integrations.sysforge.services.sku import SkuConflictError
from integrations.sysforge.services import price_history as price_history_service
from integrations.sysforge.services.price_history import PriceHistoryValidationError
from integrations.sysforge.services import stock as stock_service
from integrations.sysforge.services.stock import StockError, StockNotFoundError
from integrations.sysforge.services import suppliers as supplier_service
from integrations.sysforge.services.suppliers import (
    SupplierNameConflictError,
    SupplierValidationError,
)
from integrations.sysforge.services import clients as client_service
from integrations.sysforge.services.client_query import ClientValidationError
from integrations.sysforge.services import client_merge as client_merge_service
from integrations.sysforge.services.client_merge import ClientMergeError
from integrations.sysforge.services import invoices as invoice_service
from integrations.sysforge.services.invoice_validation import InvoiceValidationError
from integrations.sysforge.services.invoices import (
    InvoiceForeignKeyError,
    InvoiceNotFoundError,
)
from integrations.sysforge.pdf_invoice import suggested_pdf_filename
from integrations.sysforge.services import invoice_documents
from integrations.sysforge.services import invoice_email
from integrations.sysforge.services.invoice_email import InvoiceEmailError
from integrations.sysforge.services import payments as payments_service
from integrations.sysforge.services.payments import (
    PaymentNotFoundError,
    PaymentValidationError,
)
from integrations.sysforge.services import reports as reports_service
from integrations.sysforge.services.reports import ReportValidationError
from integrations.sysforge.services import invoice_devices as invoice_devices_service
from integrations.sysforge.services.invoice_devices import InvoiceDeviceError
from integrations.sysforge.services import work_orders as work_order_service
from integrations.sysforge.services.work_orders import (
    WorkOrderError,
    WorkOrderNotFoundError,
)
from integrations.sysforge.services import projects as project_service
from integrations.sysforge.services.projects import ProjectError, ProjectNotFoundError
from integrations.sysforge.services import create_project_from_invoice as create_from_invoice
from integrations.sysforge.services.create_project_from_invoice import CreateFromInvoiceError
from integrations.sysforge.services import screw_maps as screw_map_service
from integrations.sysforge.services.screw_maps import (
    ScrewMapError,
    ScrewMapLockedError,
    ScrewMapNotFoundError,
)
from src.plugins.registry import is_plugin_active, read_installed_record


def _require_sysforge_plugin(_request: Request) -> None:
    if not is_plugin_active("sysforge"):
        raise HTTPException(404, "Business Management plugin is not installed")


def _may_reveal_absolute_path(request: Request) -> bool:
    """True when require_admin would allow (auth off, or configured admin)."""
    try:
        from core.middleware import require_admin

        require_admin(request)
        return True
    except HTTPException:
        return False


class SettingsUpdate(BaseModel):
    tax_rate_percent: float | None = None
    tax_rate_bps: int | None = None
    currency: str | None = None
    autosave_drafts: bool | None = None
    autosave_interval_seconds: int | None = None
    include_archived_in_search: bool | None = None
    projects: dict[str, Any] | None = None
    companion: dict[str, Any] | None = None


class PartBody(BaseModel):
    name: str
    base_price_cents: int = 0
    description: str | None = None
    sku: str | None = None
    compatible_devices: str | None = None
    tags: str | None = None
    has_warranty: bool = False
    supplier_id: int | None = None
    preferred_supplier_id: int | None = None
    is_placeholder: bool = False


class SupplierBody(BaseModel):
    name: str
    contact_info: str | None = None
    shipping_info: str | None = None
    notes: str | None = None
    website: str | None = None
    primary_phone: str | None = None
    primary_email: str | None = None
    default_shipping_rate_cents: int = 0
    rating: int | None = None
    is_preferred: bool = False


class MergeBody(BaseModel):
    target_part_id: int
    source_part_ids: list[int] = Field(default_factory=list)


class PriceHistoryBody(BaseModel):
    price_cents: int
    source: str = "manual"
    note: str | None = None


class UpdatePriceChoice(BaseModel):
    item_id: int
    source: str = "base"
    history_id: int | None = None


class UpdatePricesPreviewBody(BaseModel):
    choices: list[UpdatePriceChoice] = Field(default_factory=list)


class UpdatePricesApplyItem(BaseModel):
    item_id: int
    proposed_cents: int


class UpdatePricesApplyBody(BaseModel):
    items: list[UpdatePricesApplyItem] = Field(default_factory=list)


class DraftRenameBody(BaseModel):
    name: str | None = None


class DraftPinBody(BaseModel):
    pinned: bool


class DraftRetentionUpdate(BaseModel):
    auto_delete_old: bool | None = None
    retention_months: int | None = None
    schedule_enabled: bool | None = None
    schedule_interval_days: int | None = None


class DraftBulkDeleteBody(BaseModel):
    ids: list[str] = Field(default_factory=list)


class ClientBody(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    nickname: str | None = None
    phone_number: str | None = None
    email: str | None = None
    address: str | None = None
    company: str | None = None
    associates: list[str] | str | None = None
    referred_by: str | None = None
    notes: str | None = None
    is_incomplete: bool = False


class ClientDuplicatesBody(BaseModel):
    phone: str | None = None
    email: str | None = None
    name: str | None = None
    exclude_id: int | None = None


class ClientMergeBody(BaseModel):
    survivor_id: int
    loser_id: int


class InvoiceItemBody(BaseModel):
    part_id: int | None = None
    part_name: str
    sku: str | None = None
    quantity_milliunits: int = 1000
    unit_price_cents: int = 0
    discount_type: str = "None"
    discount_value: int = 0
    is_taxable: bool = True
    sort_order: int = 0
    item_type: str = "Part"
    supplier_id: int | None = None


class InvoiceBody(BaseModel):
    client_id: int | None = None
    client_info: str | None = None
    name: str | None = None
    include_tax: bool = True
    include_shipping: bool = False
    tax_rate_bps: int = 775
    shipping_rate_cents: int = 0
    status: str | None = None
    is_finalized: bool | None = None
    sent_at: str | None = None
    items: list[InvoiceItemBody] = Field(default_factory=list)


class InvoiceDeviceBody(BaseModel):
    id: int | None = None
    label: str
    sort_order: int = 0


class InvoiceDevicesReplaceBody(BaseModel):
    devices: list[InvoiceDeviceBody] = Field(default_factory=list)


class AcceptEstimateBody(BaseModel):
    invoice_id: int
    bump_status_to_invoiced: bool = False


class CreateProjectFromInvoiceBody(BaseModel):
    invoice_id: int
    invoice_device_id: int
    device_id: str | None = None
    category: str = "HW"
    invoice_item_ids: list[int] = Field(default_factory=list)


class ProjectPatchBody(BaseModel):
    device_model: str | None = None
    device_serial: str | None = None
    device_color: str | None = None
    title: str | None = None


class ProjectStatusBody(BaseModel):
    status: str


class ProjectNotesBody(BaseModel):
    FirstContact: str | None = None
    ClientIssue: str | None = None
    Plan: str | None = None


class PartStockBody(BaseModel):
    quantity_on_hand: int = Field(ge=0)
    notes: str | None = None


class PartStockAdjustBody(BaseModel):
    delta: int


class PlaceScrewBody(BaseModel):
    position_x: float
    position_y: float


class PatchScrewBody(BaseModel):
    position_x: float | None = None
    position_y: float | None = None
    label: str | None = None
    notes: str | None = None
    warning_flag: bool | None = None
    length_mm: float | None = None
    shaft_diameter_mm: float | None = None
    head_diameter_mm: float | None = None
    head_type: str | None = None


class PlaceNoteBody(BaseModel):
    position_x: float
    position_y: float
    note_text: str | None = None


class PatchNoteBody(BaseModel):
    position_x: float | None = None
    position_y: float | None = None
    note_text: str | None = None


class PublishScrewMapBody(BaseModel):
    title: str
    tags: str | list[str] | None = None
    notes: str | None = None


class CloneLibrarySetBody(BaseModel):
    set_id: int


class MeasurementLookupBody(BaseModel):
    length_mm: float | None = None
    shaft_diameter_mm: float | None = None
    head_diameter_mm: float | None = None
    max_results: int = 3


class InvoiceEmailBody(BaseModel):
    to: str | None = None
    subject: str | None = None
    body: str | None = None
    body_html: str | None = None
    account_id: str | None = None


class PaymentBody(BaseModel):
    amount_cents: int
    method: str
    reference: str | None = None
    received_at: str | None = None
    notes: str | None = None


class PaymentVoidBody(BaseModel):
    reason: str


def _sku_conflict_response(exc: SkuConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content=exc.to_dict())


def _supplier_name_conflict_response(exc: SupplierNameConflictError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "code": "supplier_name_conflict",
            "name": exc.name,
            "conflicting_supplier": exc.conflicting,
        },
    )


def _public_draft(draft: dict[str, Any]) -> dict[str, Any]:
    """Strip filesystem path before returning to clients."""
    dto = list_item_dto(draft)
    out = {k: v for k, v in draft.items() if k != "filePath"}
    out["displayName"] = dto["displayName"]
    out["itemCount"] = dto["itemCount"]
    return out


def _matches_query(draft: dict[str, Any], q: str) -> bool:
    needle = q.strip().lower()
    if not needle:
        return True
    dto = list_item_dto(draft)
    hay = " ".join(
        str(x or "")
        for x in (
            draft.get("name"),
            dto["displayName"],
            draft.get("clientName"),
            draft.get("clientPhone"),
        )
    ).lower()
    return needle in hay


def setup_sysforge_routes() -> APIRouter:
    router = APIRouter(
        prefix="/api/sysforge",
        tags=["sysforge"],
        dependencies=[Depends(_require_sysforge_plugin)],
    )

    @router.get("/status")
    def status():
        # Lazy ensure: upgrades apply new SQL without a full reinstall.
        try:
            ensure_schema()
        except ChecksumMismatchError as exc:
            raise HTTPException(
                status_code=500,
                detail=exc.to_dict(),
            ) from exc
        except MigrationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        installed = read_installed_record("sysforge") or {}
        cfg = load_config()
        return {
            "ok": True,
            "plugin_id": "sysforge",
            "installed": True,
            "version": installed.get("version"),
            "installed_at": installed.get("installed_at"),
            "schema": schema_status(),
            "autosave_drafts": bool(cfg.get("autosave_drafts", True)),
            "autosave_interval_seconds": int(cfg.get("autosave_interval_seconds", 60)),
        }

    @router.get("/diagnostics")
    def diagnostics(
        request: Request,
        reveal_path: int = Query(0, ge=0, le=1),
    ):
        """Read-only plugin DB snapshot. No DebugLog; no writes; path redacted by default."""
        allow_absolute = reveal_path == 1 and _may_reveal_absolute_path(request)
        return collect_diagnostics(reveal_path=allow_absolute)

    @router.get("/settings")
    def get_settings():
        return settings_response(load_config())

    @router.put("/settings")
    def put_settings(body: SettingsUpdate):
        payload = body.model_dump(exclude_unset=True)
        try:
            cfg = save_config(payload)
        except ConfigValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return settings_response(cfg)

    # --- Clients ---

    def _ensure_clients_schema() -> None:
        try:
            ensure_schema()
        except ChecksumMismatchError as exc:
            raise HTTPException(status_code=500, detail=exc.to_dict()) from exc
        except MigrationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/clients")
    def list_clients(incomplete: int | None = Query(None)):
        _ensure_clients_schema()
        incomplete_only = incomplete == 1
        return {
            "clients": client_service.list_clients(incomplete_only=incomplete_only),
        }

    @router.get("/clients/search")
    def search_clients(
        q: str = Query(""),
        limit: int = Query(20, ge=1, le=50),
    ):
        _ensure_clients_schema()
        return {
            "query": q,
            "results": client_service.search_clients(q, limit=limit),
        }

    @router.get("/clients/recent")
    def recent_clients(limit: int = Query(6, ge=1, le=20)):
        """Persistent MRU: LastInteractedAt DESC; empty list if none touched."""
        _ensure_clients_schema()
        return {
            "clients": client_service.get_recent_clients(limit=limit),
        }

    @router.post("/clients/duplicates")
    def client_duplicates(body: ClientDuplicatesBody):
        _ensure_clients_schema()
        return {
            "duplicates": client_service.find_potential_duplicates(
                phone=body.phone,
                email=body.email,
                name=body.name,
                exclude_id=body.exclude_id,
            ),
        }

    @router.get("/clients/merge/candidates")
    def client_merge_candidates(
        client_id: int | None = Query(None),
        phone: str | None = Query(None),
        email: str | None = Query(None),
        name: str | None = Query(None),
    ):
        """Detect-only duplicate candidates for the merge tool (never auto-merges)."""
        _ensure_clients_schema()
        try:
            return {
                "candidates": client_merge_service.merge_candidates(
                    client_id=client_id,
                    phone=phone,
                    email=email,
                    name=name,
                )
            }
        except ClientMergeError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/clients/merge")
    def client_merge(body: ClientMergeBody):
        _ensure_clients_schema()
        try:
            return client_merge_service.merge_clients(
                body.survivor_id,
                body.loser_id,
            )
        except ClientMergeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/clients/{client_id}/touch")
    def touch_client(client_id: int):
        if client_id < 1:
            raise HTTPException(400, "Invalid client id")
        _ensure_clients_schema()
        client = client_service.touch_client_interaction(client_id)
        if client is None:
            raise HTTPException(404, "Client not found")
        return {
            "id": client["id"],
            "last_interacted_at": client.get("last_interacted_at"),
        }

    @router.get("/clients/{client_id}")
    def get_client(client_id: int):
        if client_id < 1:
            raise HTTPException(400, "Invalid client id")
        _ensure_clients_schema()
        client = client_service.get_client(client_id)
        if client is not None:
            return client
        merged = client_merge_service.resolve_merged_client(client_id)
        if merged is not None:
            return JSONResponse(status_code=409, content=merged)
        raise HTTPException(404, "Client not found")

    @router.post("/clients", status_code=201)
    def create_client(body: ClientBody):
        _ensure_clients_schema()
        try:
            return client_service.add_client(body.model_dump())
        except ClientValidationError as exc:
            raise HTTPException(400, detail=str(exc)) from exc

    @router.put("/clients/{client_id}")
    @router.patch("/clients/{client_id}")
    def put_client(client_id: int, body: ClientBody):
        if client_id < 1:
            raise HTTPException(400, "Invalid client id")
        _ensure_clients_schema()
        existing = client_service.get_client(client_id)
        if existing is None:
            raise HTTPException(404, "Client not found")
        payload = {**existing, **body.model_dump(exclude_unset=True)}
        for key in (
            "id",
            "date_added",
            "last_updated",
            "display_name",
            "last_interacted_at",
            "is_deleted",
            "merged_into_client_id",
        ):
            payload.pop(key, None)
        try:
            updated = client_service.update_client(client_id, payload)
        except ClientValidationError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(404, "Client not found")
        return updated

    @router.delete("/clients/{client_id}")
    def delete_client(client_id: int):
        if client_id < 1:
            raise HTTPException(400, "Invalid client id")
        _ensure_clients_schema()
        if not client_service.soft_delete_client(client_id):
            raise HTTPException(404, "Client not found")
        return {"ok": True, "id": client_id, "deleted": True}

    @router.get("/clients/{client_id}/invoices")
    def list_client_invoices(
        client_id: int,
        include_estimates: bool = Query(True),
    ):
        if client_id < 1:
            raise HTTPException(400, "Invalid client id")
        _ensure_clients_schema()
        if client_service.get_client(client_id) is None:
            raise HTTPException(404, "Client not found")
        return {
            "invoices": invoice_service.list_invoices_for_client(
                client_id,
                include_estimates=include_estimates,
            )
        }

    # --- Drafts (file-based; retention gated — draft-retention-draft-08) ---

    @router.get("/drafts")
    def list_drafts(q: str | None = None, clientId: int | None = None):
        service = get_draft_service()
        # Lazy scheduled retention (no-op when auto_delete_old / schedule off).
        service.maybe_run_scheduled_retention()
        drafts = service.get_all_drafts()
        items = []
        for draft in drafts:
            if clientId is not None and draft.get("clientId") != clientId:
                continue
            if q and not _matches_query(draft, q):
                continue
            items.append(list_item_dto(draft))
        return {"ok": True, "drafts": items}

    @router.post("/drafts")
    def create_draft(body: dict[str, Any]):
        try:
            draft = get_draft_service().save_draft(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail="Unable to access draft files"
            ) from exc
        return {"ok": True, "draft": _public_draft(draft)}

    @router.post("/drafts/delete")
    def bulk_delete_drafts(body: DraftBulkDeleteBody):
        ids = [str(i) for i in (body.ids or []) if i]
        deleted = get_draft_service().delete_drafts(ids)
        return {
            "ok": True,
            "deleted": deleted,
            "requested": len(ids),
            "message": f"Deleted {deleted} of {len(ids)} draft(s)",
        }

    @router.put("/drafts/autosave")
    def put_autosave(body: dict[str, Any]):
        try:
            draft = get_draft_service().save_autosave(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail="Unable to access draft files"
            ) from exc
        return {"ok": True, "draft": _public_draft(draft)}

    @router.get("/drafts/autosave/latest")
    def get_autosave_latest():
        draft = get_draft_service().load_autosave()
        if draft is None or draft.get("invoiceWasSaved"):
            return Response(status_code=204)
        return {"ok": True, "draft": _public_draft(draft)}

    @router.delete("/drafts/autosave")
    def delete_autosaves():
        get_draft_service().clear_autosaves()
        return {"ok": True}

    @router.get("/drafts/retention")
    def drafts_retention_get():
        service = get_draft_service()
        scheduled = service.maybe_run_scheduled_retention()
        settings = service.get_retention_config()
        out: dict[str, Any] = {"ok": True, **settings}
        if scheduled and scheduled.get("deleted", 0) > 0:
            out["scheduled_notice"] = scheduled.get("notice")
        return out

    @router.put("/drafts/retention")
    def drafts_retention_put(body: DraftRetentionUpdate):
        partial = body.model_dump(exclude_none=True)
        try:
            drafts = save_drafts_retention(partial)
        except ConfigValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "ok": True,
            "auto_delete_old": bool(drafts.get("auto_delete_old", False)),
            "retention_months": int(drafts.get("retention_months", 6)),
            "schedule_enabled": bool(drafts.get("schedule_enabled", False)),
            "schedule_interval_days": int(drafts.get("schedule_interval_days", 7)),
            "last_cleanup_at": drafts.get("last_cleanup_at"),
            "last_cleanup_deleted": int(drafts.get("last_cleanup_deleted", 0) or 0),
        }

    @router.get("/drafts/retention/preview")
    def drafts_retention_preview(
        months: int | None = Query(None, ge=1, le=60),
    ):
        return {
            "ok": True,
            **get_draft_service().preview_old_drafts(retention_months=months),
        }

    @router.post("/drafts/retention/cleanup")
    def drafts_retention_cleanup():
        """Execute cleanup. Requires auto_delete_old; returns 200 + reason when off."""
        result = get_draft_service().cleanup_old_drafts()
        return {"ok": True, **result}

    @router.get("/drafts/{draft_id}")
    def get_draft(draft_id: str):
        draft = get_draft_service().load_draft_by_id(draft_id)
        if draft is None:
            if draft_id == "autosave":
                latest = get_draft_service().load_autosave()
                if latest is None or latest.get("invoiceWasSaved"):
                    raise HTTPException(status_code=404, detail="Draft not found")
                return {"ok": True, "draft": _public_draft(latest)}
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"ok": True, "draft": _public_draft(draft)}

    @router.put("/drafts/{draft_id}")
    def put_draft(draft_id: str, body: dict[str, Any]):
        payload = dict(body or {})
        payload["id"] = draft_id
        try:
            draft = get_draft_service().save_draft(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail="Unable to access draft files"
            ) from exc
        return {"ok": True, "draft": _public_draft(draft)}

    @router.patch("/drafts/{draft_id}/pin")
    def patch_draft_pin(draft_id: str, body: DraftPinBody):
        try:
            draft = get_draft_service().set_pinned(draft_id, body.pinned)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail="Unable to access draft files"
            ) from exc
        return {"ok": True, "draft": _public_draft(draft)}

    @router.patch("/drafts/{draft_id}")
    def patch_draft(draft_id: str, body: DraftRenameBody):
        try:
            draft = get_draft_service().rename_draft(draft_id, body.name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail="Unable to access draft files"
            ) from exc
        return {"ok": True, "draft": _public_draft(draft)}

    @router.delete("/drafts/{draft_id}")
    def delete_draft(draft_id: str):
        deleted = get_draft_service().delete_draft(draft_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Draft not found")
        return {"ok": True}

    # --- Parts ---

    @router.get("/parts")
    def list_parts(
        placeholders: str = Query("all", pattern="^(0|1|all)$"),
    ):
        return {"items": parts_service.list_parts(placeholders=placeholders)}

    @router.get("/parts/search")
    def search_parts(
        q: str = Query(""),
        include_placeholders: bool = True,
        mode: str = Query("full", pattern="^(full|autocomplete)$"),
        limit: int = Query(10, ge=1, le=100),
    ):
        return {
            "items": parts_service.search_parts(
                q,
                include_placeholders=include_placeholders,
                mode=mode,
                limit=limit,
            )
        }

    @router.post("/parts/search/rebuild")
    def rebuild_parts_search():
        try:
            counts = parts_service.rebuild_parts_fts()
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Parts search rebuild failed: {exc}"
            ) from exc
        return counts

    @router.get("/parts/placeholders")
    def list_parts_placeholders():
        """Triage queue: placeholders with usage counts."""
        return {"items": parts_service.list_placeholder_triage()}

    @router.post("/parts/placeholders/{part_id}/convert")
    def convert_placeholder_triage(part_id: int, body: PartBody):
        try:
            parts_service.convert_placeholder_to_full_part(part_id, body.model_dump())
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SkuConflictError as exc:
            return _sku_conflict_response(exc)
        except PartValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(status_code=204)

    @router.get("/parts/{part_id}")
    def get_part(part_id: int):
        part = parts_service.get_part(part_id)
        if part is None:
            raise HTTPException(404, "Part not found")
        return part

    @router.get("/parts/{part_id}/price-history")
    def part_price_history(
        part_id: int,
        limit: int = Query(50, ge=1, le=200),
    ):
        if parts_service.get_part(part_id) is None:
            raise HTTPException(404, "Part not found")
        return {
            "items": price_history_service.get_part_price_history(
                part_id, limit=limit
            )
        }

    @router.post("/parts/{part_id}/price-history")
    def add_part_price_history(part_id: int, body: PriceHistoryBody):
        try:
            entry_id = price_history_service.add_part_price_history(
                part_id,
                body.price_cents,
                source=body.source,
                note=body.note,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PriceHistoryValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": entry_id}

    @router.get("/parts/{part_id}/usage")
    def part_usage(part_id: int):
        if parts_service.get_part(part_id) is None:
            raise HTTPException(404, "Part not found")
        return {"count": parts_service.get_part_usage_count(part_id)}

    @router.get("/parts/{part_id}/stock")
    def get_part_stock(part_id: int):
        ensure_schema()
        stock = stock_service.get_stock(part_id)
        if stock is None:
            raise HTTPException(404, "Part not found")
        return stock

    @router.put("/parts/{part_id}/stock")
    def put_part_stock(part_id: int, body: PartStockBody):
        ensure_schema()
        try:
            return stock_service.set_on_hand(
                part_id,
                body.quantity_on_hand,
                notes=body.notes,
            )
        except StockNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StockError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.patch("/parts/{part_id}/stock")
    def patch_part_stock(part_id: int, body: PartStockAdjustBody):
        ensure_schema()
        try:
            return stock_service.adjust_on_hand(part_id, body.delta)
        except StockNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StockError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/parts")
    def create_part(body: PartBody):
        try:
            part_id = parts_service.add_part(body.model_dump())
        except SkuConflictError as exc:
            return _sku_conflict_response(exc)
        except PartValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": part_id}

    @router.put("/parts/{part_id}")
    def put_part(part_id: int, body: PartBody):
        try:
            parts_service.update_part(part_id, body.model_dump())
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SkuConflictError as exc:
            return _sku_conflict_response(exc)
        except PartValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(status_code=204)

    @router.delete("/parts/{part_id}")
    def remove_part(part_id: int):
        if not parts_service.delete_part(part_id):
            raise HTTPException(404, "Part not found")
        return Response(status_code=204)

    @router.post("/parts/{part_id}/convert")
    def convert_part(part_id: int, body: PartBody):
        try:
            parts_service.convert_placeholder_to_full_part(part_id, body.model_dump())
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SkuConflictError as exc:
            return _sku_conflict_response(exc)
        except PartValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(status_code=204)

    # --- Suppliers ---

    @router.get("/suppliers")
    def list_suppliers(q: str | None = None):
        return {"items": supplier_service.list_suppliers(q=q)}

    @router.get("/suppliers/search")
    def search_suppliers(
        q: str = Query(""),
        limit: int = Query(10, ge=1, le=50),
    ):
        return {
            "items": supplier_service.search_suppliers(q, limit=limit),
        }

    @router.get("/suppliers/{supplier_id}")
    def get_supplier(supplier_id: int):
        supplier = supplier_service.get_supplier(supplier_id)
        if supplier is None:
            raise HTTPException(404, "Supplier not found")
        return supplier

    @router.get("/suppliers/{supplier_id}/parts")
    def supplier_parts(supplier_id: int):
        try:
            return {"items": supplier_service.get_parts_by_supplier(supplier_id)}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/suppliers")
    def create_supplier(body: SupplierBody):
        try:
            supplier_id = supplier_service.add_supplier(body.model_dump())
        except SupplierNameConflictError as exc:
            return _supplier_name_conflict_response(exc)
        except SupplierValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"id": supplier_id}

    @router.put("/suppliers/{supplier_id}")
    def put_supplier(supplier_id: int, body: SupplierBody):
        try:
            supplier_service.update_supplier(supplier_id, body.model_dump())
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except SupplierNameConflictError as exc:
            return _supplier_name_conflict_response(exc)
        except SupplierValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return Response(status_code=204)

    @router.delete("/suppliers/{supplier_id}")
    def remove_supplier(supplier_id: int):
        if not supplier_service.delete_supplier(supplier_id):
            raise HTTPException(404, "Supplier not found")
        return Response(status_code=204)

    # --- Placeholders ---

    @router.get("/placeholders")
    def list_placeholders():
        return {"items": parts_service.list_placeholder_triage()}

    @router.get("/placeholders/groups")
    def placeholder_groups():
        return {"groups": parts_service.get_placeholder_groups()}

    @router.post("/placeholders/merge")
    def merge_placeholders(body: MergeBody):
        if not body.source_part_ids:
            raise HTTPException(400, "source_part_ids must contain at least one id")
        try:
            merged = parts_service.merge_placeholders(
                body.source_part_ids,
                body.target_part_id,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"merged": merged}

    # --- Invoices (create / same-id edit / save-as-new; orphan cleanup after re-insert) ---

    def _ensure_invoice_schema() -> None:
        try:
            ensure_schema()
        except ChecksumMismatchError as exc:
            raise HTTPException(status_code=500, detail=exc.to_dict()) from exc
        except MigrationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    def _items_payload(body: InvoiceBody) -> list[dict[str, Any]]:
        return [item.model_dump() for item in body.items]

    def _invoice_exc(exc: Exception) -> None:
        if isinstance(exc, InvoiceValidationError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if isinstance(exc, InvoiceNotFoundError):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if isinstance(exc, InvoiceForeignKeyError):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "foreign_key",
                    "detail": str(exc),
                    "message": str(exc),
                },
            ) from exc
        if isinstance(exc, SkuConflictError):
            raise HTTPException(status_code=409, detail=exc.to_dict()) from exc
        raise exc

    @router.get("/invoices")
    def list_invoices(client_id: int | None = Query(None)):
        _ensure_invoice_schema()
        if client_id is None:
            raise HTTPException(400, "client_id query parameter is required")
        if client_id < 1:
            raise HTTPException(400, "Invalid client id")
        return {
            "invoices": invoice_service.list_invoices_for_client(client_id),
        }

    @router.get("/invoices/outstanding")
    def list_outstanding_invoices():
        """Invoices with balance > 0 after non-voided payments."""
        _ensure_invoice_schema()
        return {"invoices": payments_service.list_outstanding()}

    @router.get("/reports/sales")
    def reports_sales(
        request: Request,
        date_from: str | None = Query(None, alias="from"),
        date_to: str | None = Query(None, alias="to"),
        format: str | None = Query(None),
    ):
        """Date-range sales/tax summary. JSON default; ``?format=csv`` or Accept text/csv."""
        _ensure_invoice_schema()
        want_csv = (format or "").strip().lower() == "csv"
        if not want_csv:
            accept = (request.headers.get("accept") or "").lower()
            want_csv = "text/csv" in accept and "application/json" not in accept
        try:
            if want_csv:
                body = reports_service.sales_report_csv(
                    date_from=date_from, date_to=date_to
                )
                return Response(
                    content=body,
                    media_type="text/csv; charset=utf-8",
                    headers={
                        "Content-Disposition": (
                            'attachment; filename="sysforge-sales-report.csv"'
                        ),
                    },
                )
            return reports_service.sales_report(
                date_from=date_from, date_to=date_to
            )
        except ReportValidationError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.get("/invoices/{invoice_id}")
    def get_invoice(invoice_id: int):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        inv = invoice_service.get_invoice(invoice_id)
        if inv is None:
            raise HTTPException(404, "Invoice not found")
        return inv

    @router.get("/invoices/{invoice_id}/price-compare")
    def invoice_price_compare(invoice_id: int):
        """Finalized invoices: line unit cents vs catalog BasePriceCents. Estimates → []."""
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        inv = invoice_service.get_invoice(invoice_id)
        if inv is None:
            raise HTTPException(404, "Invoice not found")
        return {
            "items": invoice_service.compare_invoice_prices(invoice_id),
        }

    @router.post("/invoices/{invoice_id}/update-prices/preview")
    def update_prices_preview(
        invoice_id: int,
        body: UpdatePricesPreviewBody | None = None,
    ):
        """Propose line price deltas from catalog base or history. Gate: not finalized/Invoiced."""
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        payload = body or UpdatePricesPreviewBody()
        try:
            rows = invoice_service.preview_update_prices(
                invoice_id,
                choices=[c.model_dump() for c in payload.choices],
            )
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except InvoiceValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"items": rows}

    @router.post("/invoices/{invoice_id}/update-prices/apply")
    def update_prices_apply(invoice_id: int, body: UpdatePricesApplyBody):
        """Apply confirmed unit prices; recalculate totals. Gate: not finalized/Invoiced."""
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        try:
            inv = invoice_service.apply_update_prices(
                invoice_id,
                [item.model_dump() for item in body.items],
            )
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except InvoiceValidationError as exc:
            raise HTTPException(400, str(exc)) from exc
        return inv

    @router.get("/invoices/{invoice_id}/pdf")
    def download_invoice_pdf(invoice_id: int, persist: bool = Query(True)):
        """Generate invoice PDF (optionally persist under documents/)."""
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        try:
            if persist:
                pdf_bytes, invoice, _doc = invoice_documents.generate_and_persist(
                    invoice_id
                )
            else:
                from integrations.sysforge.pdf_invoice import generate_invoice_pdf

                pdf_bytes, invoice = generate_invoice_pdf(invoice_id)
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        filename = suggested_pdf_filename(invoice)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @router.post("/invoices/{invoice_id}/email")
    def email_invoice(invoice_id: int, body: InvoiceEmailBody, request: Request):
        """Attach PDF and send via host SMTP stack; set SentAt on success."""
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        owner = ""
        try:
            from src.auth_helpers import get_current_user

            owner = get_current_user(request) or ""
        except Exception:
            owner = ""
        try:
            return invoice_email.send_invoice_email(
                invoice_id,
                to=body.to,
                subject=body.subject,
                body=body.body,
                body_html=body.body_html,
                account_id=body.account_id,
                owner=owner,
            )
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except InvoiceEmailError as exc:
            msg = str(exc)
            lower = msg.lower()
            if "required" in lower or "recipient" in lower:
                raise HTTPException(400, msg) from exc
            raise HTTPException(status_code=502, detail=msg) from exc

    @router.get("/invoices/{invoice_id}/payments")
    def list_invoice_payments(invoice_id: int):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        try:
            return payments_service.list_payments(invoice_id)
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/invoices/{invoice_id}/payments", status_code=201)
    def create_invoice_payment(invoice_id: int, body: PaymentBody):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        try:
            return payments_service.add_payment(
                invoice_id,
                amount_cents=body.amount_cents,
                method=body.method,
                reference=body.reference,
                received_at=body.received_at,
                notes=body.notes,
            )
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PaymentValidationError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/payments/{payment_id}/void")
    def void_invoice_payment(payment_id: int, body: PaymentVoidBody):
        if payment_id < 1:
            raise HTTPException(400, "Invalid payment id")
        _ensure_invoice_schema()
        try:
            return payments_service.void_payment(payment_id, reason=body.reason)
        except PaymentNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PaymentValidationError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/invoices", status_code=201)
    def create_invoice(body: InvoiceBody):
        _ensure_invoice_schema()
        try:
            return invoice_service.create_invoice(
                body.model_dump(exclude={"items"}),
                _items_payload(body),
            )
        except Exception as exc:
            _invoice_exc(exc)
            raise

    @router.put("/invoices/{invoice_id}")
    def put_invoice(invoice_id: int, body: InvoiceBody):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        # exclude_unset so omitted status/name fields preserve DB values.
        dumped = body.model_dump(exclude_unset=True)
        status_fields = {
            k for k in ("status", "is_finalized", "sent_at") if k in dumped
        }
        payload = {k: v for k, v in dumped.items() if k != "items"}
        try:
            return invoice_service.update_invoice(
                invoice_id,
                payload,
                _items_payload(body),
                status_fields_set=status_fields,
            )
        except Exception as exc:
            _invoice_exc(exc)
            raise

    @router.post("/invoices/{invoice_id}/save-as-new", status_code=201)
    def save_invoice_as_new(invoice_id: int, body: InvoiceBody):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        try:
            return invoice_service.save_as_new(
                invoice_id,
                body.model_dump(exclude={"items"}),
                _items_payload(body),
            )
        except Exception as exc:
            _invoice_exc(exc)
            raise

    @router.delete("/invoices/{invoice_id}")
    def remove_invoice(invoice_id: int):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_invoice_schema()
        if not invoice_service.delete_invoice(invoice_id):
            raise HTTPException(404, "Invoice not found")
        return Response(status_code=204)

    # --- Work orders / projects / invoice devices ---

    def _ensure_projects_schema() -> None:
        _ensure_invoice_schema()

    def _include_archived_flag(explicit: bool | None = None) -> bool:
        if explicit is not None:
            return bool(explicit)
        cfg = load_config()
        projects = cfg.get("projects") if isinstance(cfg.get("projects"), dict) else {}
        return bool(projects.get("include_archived_in_search", False))

    @router.get("/invoices/{invoice_id}/devices")
    def list_invoice_devices(invoice_id: int):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_projects_schema()
        if invoice_service.get_invoice(invoice_id) is None:
            raise HTTPException(404, "Invoice not found")
        return {"devices": invoice_devices_service.list_devices(invoice_id)}

    @router.put("/invoices/{invoice_id}/devices")
    def put_invoice_devices(invoice_id: int, body: InvoiceDevicesReplaceBody):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_projects_schema()
        if invoice_service.get_invoice(invoice_id) is None:
            raise HTTPException(404, "Invoice not found")
        try:
            devices = invoice_devices_service.save_devices(
                invoice_id,
                [d.model_dump() for d in body.devices],
            )
        except InvoiceDeviceError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"devices": devices}

    @router.get("/work-orders/{work_order_id}")
    def get_work_order(work_order_id: int):
        if work_order_id < 1:
            raise HTTPException(400, "Invalid work order id")
        _ensure_projects_schema()
        wo = work_order_service.get_work_order(work_order_id)
        if wo is None:
            raise HTTPException(404, "Work order not found")
        return wo

    @router.post("/work-orders/from-accepted-estimate", status_code=201)
    def accept_estimate(body: AcceptEstimateBody):
        if body.invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_projects_schema()
        try:
            wo_id = work_order_service.create_from_accepted_estimate(
                body.invoice_id,
                bump_status_to_invoiced=body.bump_status_to_invoiced,
            )
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except WorkOrderError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"work_order_id": wo_id}

    @router.get("/projects/hub")
    def projects_hub(
        include_archived: bool | None = Query(None),
    ):
        _ensure_projects_schema()
        flagged = _include_archived_flag(include_archived)
        return {
            "active": project_service.get_active_projects(include_archived=flagged),
            "estimates_not_accepted": work_order_service.get_estimates_not_accepted(),
            "accepted_missing": work_order_service.get_accepted_missing_projects(),
            "include_archived": flagged,
        }

    @router.get("/projects")
    def list_projects(
        q: str | None = Query(None),
        client_id: int | None = Query(None),
        recent: int | None = Query(None),
        active: int | None = Query(None),
        include_archived: bool | None = Query(None),
    ):
        _ensure_projects_schema()
        flagged = _include_archived_flag(include_archived)
        if recent is not None:
            limit = max(1, min(int(recent), 50))
            return {
                "projects": project_service.get_recent_projects(
                    limit, include_archived=flagged
                )
            }
        if active:
            return {
                "projects": project_service.get_active_projects(include_archived=flagged)
            }
        if client_id is not None:
            if client_id < 1:
                raise HTTPException(400, "Invalid client id")
            return {
                "projects": project_service.get_projects_by_client(
                    client_id, include_archived=flagged
                )
            }
        if q is not None and str(q).strip():
            return {
                "projects": project_service.search_projects(
                    str(q), include_archived=flagged
                )
            }
        return {
            "projects": project_service.get_active_projects(include_archived=flagged)
        }

    @router.get("/projects/suggest-device-id")
    def suggest_device_id():
        _ensure_projects_schema()
        return {"device_id": project_service.generate_device_id()}

    @router.get("/projects/from-invoice/preflight")
    def create_project_preflight(invoice_id: int = Query(...)):
        if invoice_id < 1:
            raise HTTPException(400, "Invalid invoice id")
        _ensure_projects_schema()
        if invoice_service.get_invoice(invoice_id) is None:
            raise HTTPException(404, "Invoice not found")
        return create_from_invoice.eligible_devices(invoice_id)

    @router.post("/projects/from-invoice", status_code=201)
    def create_project_from_invoice(body: CreateProjectFromInvoiceBody):
        if body.invoice_id < 1 or body.invoice_device_id < 1:
            raise HTTPException(400, "Invalid invoice or device id")
        _ensure_projects_schema()
        try:
            result = create_from_invoice.create_from_invoice(
                invoice_id=body.invoice_id,
                invoice_device_id=body.invoice_device_id,
                device_id=body.device_id,
                category=body.category,
                invoice_item_ids=body.invoice_item_ids,
            )
        except InvoiceNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except CreateFromInvoiceError as exc:
            status = 409 if exc.code in (
                "accept_first",
                "all_have_projects",
                "device_has_project",
            ) else 400
            raise HTTPException(
                status_code=status,
                detail={"code": exc.code, "message": str(exc), "detail": str(exc)},
            ) from exc
        except ProjectError as exc:
            raise HTTPException(400, str(exc)) from exc
        return result

    @router.get("/projects/{project_id}")
    def get_project_detail(project_id: int):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        _ensure_projects_schema()
        detail = project_service.get_detail(project_id)
        if detail is None:
            raise HTTPException(404, "Project not found")
        return detail

    @router.patch("/projects/{project_id}")
    def patch_project(project_id: int, body: ProjectPatchBody):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        _ensure_projects_schema()
        try:
            return project_service.update_device_fields(
                project_id,
                device_model=body.device_model,
                device_serial=body.device_serial,
                device_color=body.device_color,
                title=body.title,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ProjectError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.patch("/projects/{project_id}/status")
    def patch_project_status(project_id: int, body: ProjectStatusBody):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        _ensure_projects_schema()
        try:
            return project_service.update_status(project_id, body.status)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ProjectError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.put("/projects/{project_id}/notes")
    def put_project_notes(project_id: int, body: ProjectNotesBody):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        _ensure_projects_schema()
        notes = {
            k: v
            for k, v in body.model_dump().items()
            if v is not None
        }
        try:
            return {"notes": project_service.save_notes(project_id, notes)}
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/projects/{project_id}/photos")
    async def upload_project_photo(project_id: int, request: Request):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        _ensure_projects_schema()
        form = await request.form()
        phase = str(form.get("phase") or "Before")
        upload = form.get("file")
        if upload is None:
            raise HTTPException(400, "file is required")
        filename = getattr(upload, "filename", None) or "photo.bin"
        data = await upload.read()  # type: ignore[union-attr]
        mime = getattr(upload, "content_type", None)
        try:
            return project_service.add_photo(
                project_id,
                phase,
                file_name=str(filename),
                data=data,
                mime_type=mime,
            )
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ProjectError as exc:
            raise HTTPException(400, str(exc)) from exc

    # --- Screw maps (S0–S2 + lock) ---

    def _screw_map_http_error(exc: Exception) -> HTTPException:
        if isinstance(exc, ScrewMapNotFoundError):
            return HTTPException(404, str(exc))
        if isinstance(exc, ScrewMapLockedError):
            return HTTPException(409, str(exc))
        if isinstance(exc, ScrewMapError):
            msg = str(exc)
            if "maximum size" in msg.lower():
                return HTTPException(413, msg)
            return HTTPException(400, msg)
        return HTTPException(500, str(exc))

    @router.get("/projects/{project_id}/screw-map")
    def get_project_screw_map(project_id: int):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        _ensure_projects_schema()
        m = screw_map_service.get_map_for_project(project_id)
        if m is None:
            raise HTTPException(404, "Screw map not found")
        return m

    @router.post("/projects/{project_id}/screw-map", status_code=201)
    def create_project_screw_map(project_id: int):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        _ensure_projects_schema()
        try:
            return screw_map_service.create_for_project(project_id)
        except ScrewMapNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ScrewMapError as exc:
            raise HTTPException(400, str(exc)) from exc

    @router.post("/screw-maps/{screw_map_id}/images", status_code=201)
    async def upload_screw_map_image(screw_map_id: int, request: Request):
        if screw_map_id < 1:
            raise HTTPException(400, "Invalid screw map id")
        _ensure_projects_schema()
        form = await request.form()
        upload = form.get("file")
        if upload is None:
            raise HTTPException(400, "file is required")
        filename = getattr(upload, "filename", None) or "photo.bin"
        data = await upload.read()  # type: ignore[union-attr]
        mime = getattr(upload, "content_type", None)
        try:
            return screw_map_service.add_image(
                screw_map_id,
                file_name=str(filename),
                data=data,
                mime_type=mime,
            )
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    @router.get("/screw-maps/images/{image_id}/file")
    def get_screw_map_image_file(image_id: int):
        if image_id < 1:
            raise HTTPException(400, "Invalid image id")
        _ensure_projects_schema()
        img = screw_map_service.get_image_by_id(image_id)
        if img is None:
            raise HTTPException(404, "Image not found")
        path = Path(img["file_path"])
        if not path.is_file():
            raise HTTPException(404, "Image file missing")
        media = img.get("mime_type") or "application/octet-stream"
        return FileResponse(
            path,
            media_type=media,
            filename=img.get("file_name") or path.name,
        )

    @router.get("/screw-maps/{screw_map_id}/screws")
    def list_screw_map_screws(screw_map_id: int):
        if screw_map_id < 1:
            raise HTTPException(400, "Invalid screw map id")
        _ensure_projects_schema()
        if screw_map_service.get_by_id(screw_map_id) is None:
            raise HTTPException(404, "Screw map not found")
        return {"screws": screw_map_service.get_screws_for_map(screw_map_id)}

    @router.post("/screw-maps/images/{image_id}/screws", status_code=201)
    def place_screw_marker(image_id: int, body: PlaceScrewBody):
        if image_id < 1:
            raise HTTPException(400, "Invalid image id")
        _ensure_projects_schema()
        try:
            return screw_map_service.add_screw_marker(
                image_id, body.position_x, body.position_y
            )
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    @router.patch("/screw-maps/screws/{screw_id}")
    def patch_screw_marker(screw_id: int, body: PatchScrewBody):
        if screw_id < 1:
            raise HTTPException(400, "Invalid screw id")
        _ensure_projects_schema()
        fields = body.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(400, "No fields to update")
        try:
            return screw_map_service.update_screw_marker(screw_id, fields)
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    @router.delete("/screw-maps/screws/{screw_id}", status_code=204)
    def delete_screw_marker(screw_id: int):
        if screw_id < 1:
            raise HTTPException(400, "Invalid screw id")
        _ensure_projects_schema()
        try:
            screw_map_service.delete_screw_marker(screw_id)
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc
        return Response(status_code=204)

    @router.get("/screw-maps/{screw_map_id}/notes")
    def list_screw_map_notes(screw_map_id: int):
        if screw_map_id < 1:
            raise HTTPException(400, "Invalid screw map id")
        _ensure_projects_schema()
        if screw_map_service.get_by_id(screw_map_id) is None:
            raise HTTPException(404, "Screw map not found")
        return {"notes": screw_map_service.get_notes_for_map(screw_map_id)}

    @router.post("/screw-maps/images/{image_id}/notes", status_code=201)
    def place_note_marker(image_id: int, body: PlaceNoteBody):
        if image_id < 1:
            raise HTTPException(400, "Invalid image id")
        _ensure_projects_schema()
        try:
            return screw_map_service.add_note_marker(
                image_id,
                body.position_x,
                body.position_y,
                note_text=body.note_text,
            )
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    @router.patch("/screw-maps/notes/{note_id}")
    def patch_note_marker(note_id: int, body: PatchNoteBody):
        if note_id < 1:
            raise HTTPException(400, "Invalid note id")
        _ensure_projects_schema()
        fields = body.model_dump(exclude_unset=True)
        if not fields:
            raise HTTPException(400, "No fields to update")
        try:
            return screw_map_service.update_note_marker(note_id, fields)
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    @router.delete("/screw-maps/notes/{note_id}", status_code=204)
    def delete_note_marker(note_id: int):
        if note_id < 1:
            raise HTTPException(400, "Invalid note id")
        _ensure_projects_schema()
        try:
            screw_map_service.delete_note_marker(note_id)
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc
        return Response(status_code=204)

    @router.post("/screw-maps/{screw_map_id}/lock")
    def lock_screw_map(screw_map_id: int):
        if screw_map_id < 1:
            raise HTTPException(400, "Invalid screw map id")
        _ensure_projects_schema()
        try:
            return screw_map_service.lock_screw_map(screw_map_id)
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    # --- Screw map library (S4) + measurement lookup (S3) ---

    @router.get("/screw-map-library")
    def list_screw_map_library(
        device_model: str | None = None, limit: int = 20
    ):
        _ensure_projects_schema()
        if limit < 1:
            limit = 1
        if limit > 100:
            limit = 100
        sets = screw_map_service.get_library_sets_for_model(
            device_model, max_results=limit
        )
        return {"sets": sets}

    @router.post("/screw-maps/{screw_map_id}/publish", status_code=201)
    def publish_screw_map(screw_map_id: int, body: PublishScrewMapBody):
        if screw_map_id < 1:
            raise HTTPException(400, "Invalid screw map id")
        _ensure_projects_schema()
        try:
            return screw_map_service.publish_to_library(
                screw_map_id,
                body.title,
                tags=body.tags,
                notes=body.notes,
            )
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    @router.post("/projects/{project_id}/screw-map/clone-from-library", status_code=201)
    def clone_screw_map_from_library(project_id: int, body: CloneLibrarySetBody):
        if project_id < 1:
            raise HTTPException(400, "Invalid project id")
        if body.set_id < 1:
            raise HTTPException(400, "Invalid set id")
        _ensure_projects_schema()
        try:
            return screw_map_service.clone_library_set_into_project(
                body.set_id, project_id
            )
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    @router.post("/screw-maps/{screw_map_id}/measurement-matches")
    def find_screw_measurement_matches(
        screw_map_id: int, body: MeasurementLookupBody
    ):
        if screw_map_id < 1:
            raise HTTPException(400, "Invalid screw map id")
        _ensure_projects_schema()
        max_results = body.max_results
        if max_results < 1:
            max_results = 1
        if max_results > 3:
            max_results = 3
        try:
            matches = screw_map_service.find_matches_by_measurement(
                screw_map_id,
                length_mm=body.length_mm,
                shaft_diameter_mm=body.shaft_diameter_mm,
                head_diameter_mm=body.head_diameter_mm,
                max_results=max_results,
            )
            return {"matches": matches}
        except Exception as exc:
            raise _screw_map_http_error(exc) from exc

    # Business backup / restore (plugin-scoped; not Odysseus /api/export)
    from integrations.sysforge.routes_backup import register_backup_routes

    register_backup_routes(router)

    # S5 mobile companion (desk + phone)
    from integrations.sysforge.routes_companion import register_companion_routes

    register_companion_routes(router)

    return router
