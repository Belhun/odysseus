"""Finance routes — accounts, import, transactions, budgets, reports."""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from integrations.finance.database import get_session_factory, init_finance_db
from integrations.finance.models import (
    FinanceCategory,
    FinanceImportBatch,
    FinanceTransaction,
)
from integrations.finance.services.accounts import (
    account_dict,
    create_account_for_owner,
    delete_account_for_owner,
    list_accounts_for_owner,
    patch_account_for_owner,
    pin_account_balances,
)
from integrations.finance.services.budgets import (
    copy_budgets_for_owner,
    get_income_target,
    set_income_target,
    upsert_budget_for_owner,
)
from integrations.finance.services.planned import (
    create_planned_for_owner,
    delete_planned_for_owner,
    get_job_scenario,
    job_overlay,
    list_planned_for_owner,
    planned_dict,
    upsert_job_scenario,
)
from integrations.finance.services.categories import (
    create_category_for_owner,
    create_rule_for_owner,
    delete_rule_for_owner,
    ensure_default_categories,
    format_category_path,
    list_rules_for_owner,
    ordered_category_list,
)
from integrations.finance.services.import_service import (
    build_import_preview,
    commit_import_preview,
    rollback_import_batch,
)
from integrations.finance.services.wells_statement_pdf import (
    WellsStatementError,
    convert_wells_statement_uploads,
    format_convert_report,
    format_dollars,
    result_to_csv,
    suggested_account_fields,
)
from integrations.finance.services.mappings import (
    list_mappings_for_owner,
    mapping_dict,
    parse_json_object,
    save_mapping_for_owner,
)
from integrations.finance.services.reports import validate_month
from integrations.finance.services.recurring import list_recurring_series, patch_recurring_series
from integrations.finance.services.movements import (
    bulk_classify_transactions,
    classify_transaction,
    detect_movements,
    link_movements,
    movement_candidates,
    unlink_movement,
)
from integrations.finance.services.reports import (
    AVERAGE_LOOKBACK_MONTHS,
    category_spend_averages,
    month_cashflow,
    month_key,
    month_review,
    monthly_trends,
    net_worth,
    spend_by_account,
    spending_by_category,
)
from integrations.finance.services.transactions import (
    MAX_TRANSACTION_SPLITS,
    ImportedTransactionError,
    apply_transaction_filters,
    clear_transaction_splits,
    create_manual_transaction,
    delete_manual_transaction,
    list_payees_for_owner,
    list_transaction_splits,
    patch_ledger_transaction,
    set_transaction_splits,
    split_counts_for_transactions,
    unvoid_transaction,
    void_transaction,
)
from src.auth_helpers import effective_user, require_user as _session_require_user
from src.plugins.registry import is_plugin_active, is_plugin_installed
from src.upload_limits import (
    FINANCE_IMPORT_MAX_BYTES,
    FINANCE_STATEMENT_BATCH_MAX_BYTES,
    FINANCE_STATEMENT_FILE_MAX_BYTES,
    FINANCE_STATEMENT_MAX_FILES,
    format_byte_limit,
    read_upload_limited,
)

_FINANCE_READ_SCOPES = {"finance:read", "finance:write"}


def _finance_token_scopes(request: Request) -> set[str]:
    scopes = getattr(request.state, "api_token_scopes", None) or []
    if isinstance(scopes, str):
        scopes = [s.strip() for s in scopes.split(",")]
    return {str(s).strip() for s in scopes if str(s).strip()}


def require_user(request: Request) -> str:
    """Owner for finance routes.

    Cookie sessions use the normal user gate. Bearer ``ody_`` tokens must
    carry ``finance:read`` (GET/HEAD) or ``finance:write`` (mutating methods)
    and resolve to the token owner so a Tailscale phone client sees the same
    ledger as the web UI.
    """
    if getattr(request.state, "api_token", False):
        scopes = _finance_token_scopes(request)
        write = request.method not in ("GET", "HEAD", "OPTIONS")
        if write:
            if "finance:write" not in scopes:
                raise HTTPException(403, "API token requires finance:write scope")
        elif not scopes.intersection(_FINANCE_READ_SCOPES):
            raise HTTPException(403, "API token requires finance:read scope")
        owner = getattr(request.state, "api_token_owner", None) or None
        if not owner:
            raise HTTPException(401, "Not authenticated")
        return owner
    return _session_require_user(request)


def _require_finance_plugin(_request: Request) -> None:
    if not is_plugin_active("finance"):
        raise HTTPException(404, "Finance plugin is not installed")


def _optional_month(month: Optional[str]) -> Optional[str]:
    if not month:
        return None
    try:
        return validate_month(month)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def require_finance_user(request: Request) -> str:
    """Cookie sessions use require_user. Bearer ody_ tokens need finance scopes.

    Reads accept finance:read or finance:write. Writes require finance:write.
    Tests that patch require_user keep working for the non-token path.
    """
    if getattr(request.state, "api_token", False):
        scopes = set(getattr(request.state, "api_token_scopes", []) or [])
        write = request.method not in ("GET", "HEAD", "OPTIONS")
        if write:
            if "finance:write" not in scopes:
                raise HTTPException(403, "API token missing required scope: finance:write")
        elif "finance:read" not in scopes and "finance:write" not in scopes:
            raise HTTPException(403, "API token missing required scope: finance:read")
        owner = effective_user(request)
        if not owner:
            raise HTTPException(401, "Not authenticated")
        return owner
    return require_user(request)


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    institution: str = ""
    account_type: str = "checking"
    purpose: str = "operating"
    rail: Optional[str] = None
    currency: str = "USD"
    mask_last4: Optional[str] = None
    opening_balance_cents: int = 0
    opening_balance_date: Optional[str] = None
    credit_limit_cents: Optional[int] = None
    posted_pin_cents: Optional[int] = None
    posted_pin_as_of: Optional[str] = None
    available_cents: Optional[int] = None
    available_as_of: Optional[str] = None


class AccountPatch(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    account_type: Optional[str] = None
    purpose: Optional[str] = None
    rail: Optional[str] = None
    mask_last4: Optional[str] = None
    opening_balance_cents: Optional[int] = None
    opening_balance_date: Optional[str] = None
    credit_limit_cents: Optional[int] = None
    is_closed: Optional[bool] = None
    display_order: Optional[int] = None
    posted_pin_cents: Optional[int] = None
    posted_pin_as_of: Optional[str] = None
    available_cents: Optional[int] = None
    available_as_of: Optional[str] = None


class AccountPins(BaseModel):
    posted_pin_cents: Optional[int] = None
    posted_pin_as_of: Optional[str] = None
    available_cents: Optional[int] = None
    available_as_of: Optional[str] = None
    clear_posted_pin: bool = False
    clear_available: bool = False


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: Optional[str] = None
    is_income: bool = False
    color: str = "#5b8abf"


class RuleCreate(BaseModel):
    pattern: str = Field(min_length=1, max_length=200)
    category_id: Optional[str] = None
    movement_class: Optional[str] = None
    priority: int = 100
    apply_existing: bool = True
    operator: str = ""
    match_field: str = "payee"


class BudgetSet(BaseModel):
    category_id: str
    month: str
    limit_cents: int = Field(ge=0)

    def model_post_init(self, __context) -> None:
        object.__setattr__(self, "month", validate_month(self.month))


class TransactionCreate(BaseModel):
    account_id: str
    date: str
    amount_cents: int
    payee: str = ""
    memo: str = ""
    category_id: Optional[str] = None
    status: str = "cleared"
    movement_class: Optional[str] = None


class TransactionPatch(BaseModel):
    category_id: Optional[str] = None
    payee: Optional[str] = None
    memo: Optional[str] = None
    status: Optional[str] = None
    amount_cents: Optional[int] = None
    date: Optional[str] = None
    account_id: Optional[str] = None
    movement_class: Optional[str] = None


class ImportCommitBody(BaseModel):
    preview_id: str
    skip_duplicates: bool = True
    apply_opening: bool = False


class ImportPreviewTextBody(BaseModel):
    account_id: str
    text: str
    filename: str = "clipboard.csv"
    preset: Optional[str] = None
    mapping: Optional[dict] = None
    options: Optional[dict] = None
    mapping_id: Optional[str] = None


class MappingSaveBody(BaseModel):
    name: str
    fingerprint: str
    mapping: dict[str, str]
    options: Optional[dict] = None


class SplitEntry(BaseModel):
    category_id: Optional[str] = None
    amount_cents: int
    memo: str = ""


class SplitsBody(BaseModel):
    splits: list[SplitEntry] = Field(..., min_length=1, max_length=MAX_TRANSACTION_SPLITS)


class RecurringPatch(BaseModel):
    status: str
    category_id: Optional[str] = None
    movement_class: Optional[str] = None


class BudgetCopyBody(BaseModel):
    from_month: str
    to_month: str

    def model_post_init(self, __context) -> None:
        object.__setattr__(self, "from_month", validate_month(self.from_month))
        object.__setattr__(self, "to_month", validate_month(self.to_month))


class IncomeTargetBody(BaseModel):
    month: str
    income_target_cents: int = Field(ge=0)

    def model_post_init(self, __context) -> None:
        object.__setattr__(self, "month", validate_month(self.month))


class PlannedCreate(BaseModel):
    name: str
    kind: str
    amount_cents: int
    include_in_job_overlay: bool = True
    is_funding: bool = False
    notes: str = ""
    starts_on: Optional[str] = None


class JobScenarioBody(BaseModel):
    take_home_cents: int = Field(ge=0)
    label: str = "Hypothetical job"


class MovementClassifyBody(BaseModel):
    movement_class: str


class BulkClassifyBody(BaseModel):
    transaction_ids: list[str]
    movement_class: Optional[str] = None
    category_id: Optional[str] = None
    apply_to_payee: bool = False


class MovementLinkBody(BaseModel):
    tx_ids: list[str]


class MovementUnlinkBody(BaseModel):
    tx_id: Optional[str] = None
    movement_group_id: Optional[str] = None


class MovementDetectBody(BaseModel):
    account_ids: Optional[list[str]] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    day_gap: Optional[int] = None
    auto_link: bool = False


def _require_owned_category(db, user: str, category_id: str | None) -> None:
    if not category_id:
        return
    cat = db.query(FinanceCategory).filter(
        FinanceCategory.id == category_id,
        FinanceCategory.owner == user,
    ).first()
    if not cat:
        raise HTTPException(404, "Category not found")


def _transaction_dict(
    tx: FinanceTransaction,
    category_name: str | None = None,
    *,
    split_count: int = 0,
) -> dict[str, Any]:
    return {
        "id": tx.id,
        "account_id": tx.account_id,
        "date": tx.date.isoformat() if tx.date else None,
        "amount_cents": tx.amount_cents,
        "payee": tx.payee or "",
        "memo": tx.memo or "",
        "check_number": tx.check_number,
        "category_id": tx.category_id,
        "category_name": category_name,
        "status": tx.status,
        "source": tx.source or "import",
        "is_manual": (tx.source or "import") == "manual" and not tx.import_batch_id,
        "is_linked": bool(tx.movement_group_id),
        "is_split": int(split_count or 0) > 0,
        "split_count": int(split_count or 0),
        "bank_category": tx.bank_category,
        "import_batch_id": tx.import_batch_id,
        "movement_class": tx.movement_class,
        "movement_group_id": tx.movement_group_id,
        "daily_balance_cents": tx.daily_balance_cents,
        "statement_start": tx.statement_start.isoformat() if tx.statement_start else None,
        "statement_end": tx.statement_end.isoformat() if tx.statement_end else None,
        "source_statement": tx.source_statement,
    }


def setup_finance_routes() -> APIRouter:
    from integrations.finance.confirmation_gate import register_finance_confirmation_gate

    register_finance_confirmation_gate()
    if is_plugin_installed("finance"):
        init_finance_db()

    router = APIRouter(
        prefix="/api/finance",
        tags=["finance"],
        dependencies=[Depends(_require_finance_plugin)],
    )

    @router.get("/accounts")
    def list_accounts(request: Request, include_closed: bool = False):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            ensure_default_categories(db, user)
            accounts = list_accounts_for_owner(db, user, include_closed=include_closed)
            return {"accounts": [account_dict(db, a) for a in accounts]}
        finally:
            db.close()

    @router.post("/accounts")
    def create_account(request: Request, body: AccountCreate):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                account = create_account_for_owner(
                    db,
                    user,
                    name=body.name,
                    institution=body.institution,
                    account_type=body.account_type,
                    purpose=body.purpose,
                    rail=body.rail,
                    currency=body.currency,
                    mask_last4=body.mask_last4,
                    opening_balance_cents=body.opening_balance_cents,
                    opening_balance_date=body.opening_balance_date,
                    credit_limit_cents=body.credit_limit_cents,
                    posted_pin_cents=body.posted_pin_cents,
                    posted_pin_as_of=body.posted_pin_as_of,
                    available_cents=body.available_cents,
                    available_as_of=body.available_as_of,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return account_dict(db, account)
        finally:
            db.close()

    @router.patch("/accounts/{account_id}")
    def patch_account(request: Request, account_id: str, body: AccountPatch):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                account = patch_account_for_owner(
                    db,
                    user,
                    account_id,
                    name=body.name,
                    institution=body.institution,
                    account_type=body.account_type,
                    purpose=body.purpose,
                    rail=body.rail,
                    mask_last4=body.mask_last4,
                    opening_balance_cents=body.opening_balance_cents,
                    opening_balance_date=body.opening_balance_date,
                    credit_limit_cents=body.credit_limit_cents,
                    is_closed=body.is_closed,
                    display_order=body.display_order,
                    posted_pin_cents=body.posted_pin_cents,
                    posted_pin_as_of=body.posted_pin_as_of,
                    available_cents=body.available_cents,
                    available_as_of=body.available_as_of,
                )
            except ValueError as exc:
                message = str(exc)
                code = 404 if "not found" in message.lower() else 400
                raise HTTPException(code, message) from exc
            return account_dict(db, account)
        finally:
            db.close()

    @router.delete("/accounts/{account_id}")
    def delete_account(request: Request, account_id: str, purge_transactions: bool = False):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                deleted = delete_account_for_owner(
                    db, user, account_id, purge_transactions=purge_transactions
                )
            except ValueError as exc:
                code = 400 if "transactions" in str(exc) else 404
                raise HTTPException(code, str(exc)) from exc
            return {"ok": True, "deleted_transactions": deleted}
        finally:
            db.close()

    @router.post("/accounts/{account_id}/pins")
    def pin_account(request: Request, account_id: str, body: AccountPins):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                account = pin_account_balances(
                    db,
                    user,
                    account_id,
                    posted_pin_cents=body.posted_pin_cents,
                    posted_pin_as_of=body.posted_pin_as_of,
                    available_cents=body.available_cents,
                    available_as_of=body.available_as_of,
                    clear_posted_pin=body.clear_posted_pin,
                    clear_available=body.clear_available,
                )
            except ValueError as exc:
                message = str(exc)
                code = 404 if "not found" in message.lower() else 400
                raise HTTPException(code, message) from exc
            return account_dict(db, account)
        finally:
            db.close()

    @router.get("/categories")
    def list_categories(request: Request):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            ensure_default_categories(db, user)
            cats = db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()
            cats_by_id = {c.id: c for c in cats}
            return {
                "categories": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "display_name": format_category_path(c, cats_by_id),
                        "parent_id": c.parent_id,
                        "is_income": bool(c.is_income),
                        "color": c.color,
                    }
                    for c in ordered_category_list(cats)
                ]
            }
        finally:
            db.close()

    @router.post("/categories")
    def create_category(request: Request, body: CategoryCreate):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            _require_owned_category(db, user, body.parent_id)
            try:
                cat = create_category_for_owner(
                    db,
                    user,
                    body.name,
                    is_income=body.is_income,
                    color=body.color,
                    parent_id=body.parent_id,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"id": cat.id, "name": cat.name, "parent_id": cat.parent_id}
        finally:
            db.close()

    @router.get("/rules")
    def list_rules(request: Request):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            rules = list_rules_for_owner(db, user)
            return {
                "rules": [
                    {
                        "id": r.id,
                        "pattern": r.pattern,
                        "category_id": r.category_id,
                        "movement_class": r.movement_class,
                        "priority": r.priority,
                        "operator": getattr(r, "operator", None) or "",
                        "match_field": getattr(r, "match_field", None) or "payee",
                    }
                    for r in rules
                ]
            }
        finally:
            db.close()

    @router.post("/rules")
    def create_rule(request: Request, body: RuleCreate):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            if body.category_id:
                _require_owned_category(db, user, body.category_id)
            try:
                rule = create_rule_for_owner(
                    db,
                    user,
                    pattern=body.pattern,
                    category_id=body.category_id,
                    movement_class=body.movement_class,
                    priority=body.priority,
                    apply_existing=body.apply_existing,
                    operator=body.operator,
                    match_field=body.match_field,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"id": rule.id}
        finally:
            db.close()

    @router.delete("/rules/{rule_id}")
    def delete_rule(request: Request, rule_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                delete_rule_for_owner(db, user, rule_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {"ok": True}
        finally:
            db.close()

    @router.get("/transactions")
    def list_transactions(
        request: Request,
        account_id: Optional[str] = None,
        search: str = "",
        search_scope: str = "payee",
        category_id: Optional[str] = None,
        month: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_amount_cents: Optional[int] = None,
        max_amount_cents: Optional[int] = None,
        uncategorized: bool = False,
        movement_class: Optional[str] = None,
        unclassified: bool = False,
        include_void: bool = False,
        status: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        user = require_finance_user(request)
        month = _optional_month(month)
        db = get_session_factory()()
        try:
            q = apply_transaction_filters(
                db.query(FinanceTransaction),
                owner=user,
                account_id=account_id,
                category_id=category_id,
                month=month,
                search=search,
                search_scope=search_scope,
                start_date=start_date,
                end_date=end_date,
                min_amount_cents=min_amount_cents,
                max_amount_cents=max_amount_cents,
                uncategorized=uncategorized,
                movement_class=movement_class,
                unclassified=unclassified,
                include_void=include_void,
                status=status,
            )
            total = q.count()
            txs = (
                q.order_by(FinanceTransaction.date.desc(), FinanceTransaction.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            cats = db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()
            cats_by_id = {c.id: c for c in cats}
            cat_map = {c.id: format_category_path(c, cats_by_id) for c in cats}
            split_counts = split_counts_for_transactions(db, user, [tx.id for tx in txs])
            return {
                "total": total,
                "transactions": [
                    _transaction_dict(
                        tx,
                        cat_map.get(tx.category_id),
                        split_count=split_counts.get(tx.id, 0),
                    )
                    for tx in txs
                ],
            }
        finally:
            db.close()

    @router.get("/transactions/export.csv")
    def export_transactions_csv(
        request: Request,
        account_id: Optional[str] = None,
        search: str = "",
        category_id: Optional[str] = None,
        month: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_amount_cents: Optional[int] = None,
        max_amount_cents: Optional[int] = None,
        uncategorized: bool = False,
    ):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            q = apply_transaction_filters(
                db.query(FinanceTransaction),
                owner=user,
                account_id=account_id,
                category_id=category_id,
                month=month,
                search=search,
                start_date=start_date,
                end_date=end_date,
                min_amount_cents=min_amount_cents,
                max_amount_cents=max_amount_cents,
                uncategorized=uncategorized,
            )
            txs = (
                q.order_by(FinanceTransaction.date.desc(), FinanceTransaction.created_at.desc())
                .limit(50_000)
                .all()
            )
            cats = db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()
            cats_by_id = {c.id: c for c in cats}
            cat_map = {c.id: format_category_path(c, cats_by_id) for c in cats}

            def _generate():
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["date", "payee", "amount", "category", "memo", "account_id", "id"])
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
                for tx in txs:
                    dollars = f"{tx.amount_cents / 100:.2f}"
                    writer.writerow([
                        tx.date.isoformat() if tx.date else "",
                        tx.payee or "",
                        dollars,
                        cat_map.get(tx.category_id) or "Uncategorized",
                        tx.memo or "",
                        tx.account_id,
                        tx.id,
                    ])
                    yield buf.getvalue()
                    buf.seek(0)
                    buf.truncate(0)

            return StreamingResponse(
                _generate(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=transactions.csv"},
            )
        finally:
            db.close()

    @router.post("/transactions")
    def create_transaction(request: Request, body: TransactionCreate):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            _require_owned_category(db, user, body.category_id)
            try:
                tx = create_manual_transaction(
                    db,
                    user,
                    account_id=body.account_id,
                    date_raw=body.date,
                    amount_cents=body.amount_cents,
                    payee=body.payee,
                    memo=body.memo,
                    category_id=body.category_id,
                    status=body.status,
                    movement_class=body.movement_class,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return _transaction_dict(tx)
        finally:
            db.close()

    @router.patch("/transactions/{tx_id}")
    def patch_transaction(request: Request, tx_id: str, body: TransactionPatch):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            if body.category_id:
                _require_owned_category(db, user, body.category_id)
            try:
                tx = patch_ledger_transaction(
                    db,
                    user,
                    tx_id,
                    amount_cents=body.amount_cents,
                    date_raw=body.date,
                    account_id=body.account_id,
                    payee=body.payee,
                    memo=body.memo,
                    category_id=body.category_id,
                    status=body.status,
                    movement_class=body.movement_class,
                )
            except ValueError as exc:
                message = str(exc)
                code = 404 if "not found" in message.lower() else 400
                raise HTTPException(code, message) from exc
            return _transaction_dict(tx)
        finally:
            db.close()

    @router.post("/transactions/{tx_id}/void")
    def void_tx(request: Request, tx_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                tx = void_transaction(db, user, tx_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return _transaction_dict(tx)
        finally:
            db.close()

    @router.post("/transactions/{tx_id}/unvoid")
    def unvoid_tx(request: Request, tx_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                tx = unvoid_transaction(db, user, tx_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return _transaction_dict(tx)
        finally:
            db.close()

    @router.delete("/transactions/{tx_id}")
    def delete_transaction(request: Request, tx_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                delete_manual_transaction(db, user, tx_id)
            except ImportedTransactionError as exc:
                raise HTTPException(409, str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {"ok": True}
        finally:
            db.close()

    @router.put("/transactions/{tx_id}/splits")
    def put_transaction_splits(request: Request, tx_id: str, body: SplitsBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            for entry in body.splits:
                if entry.category_id:
                    _require_owned_category(db, user, entry.category_id)
            try:
                splits = set_transaction_splits(
                    db,
                    user,
                    tx_id,
                    [s.model_dump() for s in body.splits],
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {
                "splits": [
                    {
                        "id": s.id,
                        "category_id": s.category_id,
                        "amount_cents": s.amount_cents,
                        "memo": s.memo,
                    }
                    for s in splits
                ]
            }
        finally:
            db.close()

    @router.get("/transactions/{tx_id}/splits")
    def get_transaction_splits(request: Request, tx_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                splits = list_transaction_splits(db, user, tx_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {
                "splits": [
                    {
                        "id": s.id,
                        "category_id": s.category_id,
                        "amount_cents": s.amount_cents,
                        "memo": s.memo,
                    }
                    for s in splits
                ]
            }
        finally:
            db.close()

    @router.delete("/transactions/{tx_id}/splits")
    def delete_transaction_splits(request: Request, tx_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                deleted = clear_transaction_splits(db, user, tx_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {"ok": True, "deleted": deleted}
        finally:
            db.close()

    @router.get("/payees")
    def list_payees(
        request: Request,
        q: str = "",
        limit: int = Query(20, ge=1, le=50),
    ):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return {"payees": list_payees_for_owner(db, user, q=q, limit=limit)}
        finally:
            db.close()

    @router.get("/import/mappings")
    def list_import_mappings(request: Request):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return {"mappings": [mapping_dict(m) for m in list_mappings_for_owner(db, user)]}
        finally:
            db.close()

    @router.post("/import/mappings")
    def save_import_mapping(request: Request, body: MappingSaveBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            row = save_mapping_for_owner(
                db,
                user,
                name=body.name,
                fingerprint=body.fingerprint,
                mapping=body.mapping,
                options=body.options,
            )
            return mapping_dict(row)
        finally:
            db.close()

    @router.post("/import/preview")
    async def import_preview(
        request: Request,
        file: UploadFile = File(...),
        account_id: str = Form(...),
        preset: str = Form(""),
        mapping: str = Form(""),
        options: str = Form(""),
        mapping_id: str = Form(""),
    ):
        user = require_finance_user(request)
        content = await read_upload_limited(file, FINANCE_IMPORT_MAX_BYTES, "Finance import")
        try:
            mapping_obj = parse_json_object(mapping or None)
            options_obj = parse_json_object(options or None)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

        def _run_preview():
            db = get_session_factory()()
            try:
                return build_import_preview(
                    db,
                    user,
                    account_id,
                    file.filename or "import.csv",
                    content,
                    preset=preset or None,
                    mapping=mapping_obj or None,
                    options=options_obj or None,
                    mapping_id=mapping_id or None,
                )
            finally:
                db.close()

        try:
            return await asyncio.to_thread(_run_preview)
        except ValueError as err:
            raise HTTPException(400, str(err))

    @router.post("/import/preview-text")
    async def import_preview_text(request: Request, body: ImportPreviewTextBody):
        user = require_finance_user(request)
        if not (body.text or "").strip():
            raise HTTPException(400, "text is required")
        content = body.text.encode("utf-8")
        if len(content) > FINANCE_IMPORT_MAX_BYTES:
            raise HTTPException(
                413,
                f"Finance import exceeds {format_byte_limit(FINANCE_IMPORT_MAX_BYTES)} limit",
            )
        filename = (body.filename or "").strip() or "clipboard.csv"

        def _run_preview_text():
            db = get_session_factory()()
            try:
                return build_import_preview(
                    db,
                    user,
                    body.account_id,
                    filename,
                    content,
                    preset=body.preset or None,
                    mapping=body.mapping or None,
                    options=body.options or None,
                    mapping_id=body.mapping_id or None,
                )
            finally:
                db.close()

        try:
            return await asyncio.to_thread(_run_preview_text)
        except ValueError as err:
            raise HTTPException(400, str(err))

    @router.post("/statements/convert")
    async def convert_statement_pdfs(
        request: Request,
        files: list[UploadFile] = File(...),
        csv_files: list[UploadFile] | None = File(None),
    ):
        require_finance_user(request)
        if not files:
            raise HTTPException(400, "Choose one or more Wells Fargo statement PDFs")
        if len(files) > FINANCE_STATEMENT_MAX_FILES:
            raise HTTPException(
                400,
                f"Too many PDFs (max {FINANCE_STATEMENT_MAX_FILES} per convert)",
            )
        uploads: list[tuple[str, bytes]] = []
        total = 0
        for upload in files:
            data = await read_upload_limited(
                upload, FINANCE_STATEMENT_FILE_MAX_BYTES, "Statement PDF"
            )
            total += len(data)
            if total > FINANCE_STATEMENT_BATCH_MAX_BYTES:
                raise HTTPException(
                    413,
                    f"Statement batch exceeds {format_byte_limit(FINANCE_STATEMENT_BATCH_MAX_BYTES)} limit",
                )
            name = upload.filename or "statement.pdf"
            if not name.lower().endswith(".pdf"):
                raise HTTPException(400, f"{name}: upload PDF statements only")
            uploads.append((name, data))
        bank_uploads: list[tuple[str, bytes]] = []
        for upload in csv_files or []:
            data = await read_upload_limited(
                upload, FINANCE_IMPORT_MAX_BYTES, "Checking CSV"
            )
            total += len(data)
            if total > FINANCE_STATEMENT_BATCH_MAX_BYTES:
                raise HTTPException(
                    413,
                    f"Statement batch exceeds {format_byte_limit(FINANCE_STATEMENT_BATCH_MAX_BYTES)} limit",
                )
            name = upload.filename or "checking.csv"
            if not name.lower().endswith(".csv"):
                raise HTTPException(400, f"{name}: bank export must be a CSV")
            bank_uploads.append((name, data))

        def _run_convert():
            return convert_wells_statement_uploads(uploads, bank_csvs=bank_uploads)

        try:
            result = await asyncio.to_thread(_run_convert)
        except WellsStatementError as err:
            raise HTTPException(400, str(err))

        csv_text = result_to_csv(result)
        return {
            "opening_posted_cents": result.opening_posted_cents,
            "opening_as_of": result.opening_as_of.isoformat(),
            "opening_posted": format_dollars(result.opening_posted_cents),
            "last_ending_cents": result.last_ending_cents,
            "last_ending_date": result.last_ending_date.isoformat(),
            "statement_count": len(result.statements),
            "transaction_count": len(result.transactions),
            "bank_appended_count": result.bank_appended_count,
            "bank_matched_count": result.bank_matched_count,
            "warnings": result.warnings,
            "report": format_convert_report(result),
            "csv": csv_text,
            "filename": "wells-from-statements.csv",
            "suggested_account": suggested_account_fields(result),
        }

    @router.post("/import/commit")
    def import_commit(request: Request, body: ImportCommitBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            result = commit_import_preview(
                db, user, body.preview_id, skip_duplicates=body.skip_duplicates,
                apply_opening=body.apply_opening,
            )
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            db.close()

    @router.get("/import/batches")
    def list_batches(request: Request, account_id: Optional[str] = None):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            q = db.query(FinanceImportBatch).filter(FinanceImportBatch.owner == user)
            if account_id:
                q = q.filter(FinanceImportBatch.account_id == account_id)
            batches = q.order_by(FinanceImportBatch.created_at.desc()).limit(50).all()
            return {
                "batches": [
                    {
                        "id": b.id,
                        "account_id": b.account_id,
                        "filename": b.filename,
                        "format": b.format,
                        "row_count": b.row_count,
                        "imported_count": b.imported_count,
                        "duplicate_count": b.duplicate_count,
                        "created_at": b.created_at.isoformat() if b.created_at else None,
                    }
                    for b in batches
                ]
            }
        finally:
            db.close()

    @router.delete("/import/batches/{batch_id}")
    def rollback_batch(request: Request, batch_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                deleted = rollback_import_batch(db, user, batch_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {"ok": True, "deleted_transactions": deleted}
        finally:
            db.close()

    @router.get("/budgets")
    def list_budgets(
        request: Request,
        month: Optional[str] = None,
        account_id: Optional[str] = None,
        include_transfers: bool = False,
    ):
        user = require_finance_user(request)
        month = _optional_month(month) or month_key(date.today())
        db = get_session_factory()()
        try:
            ensure_default_categories(db, user)
            cashflow = month_cashflow(
                db, user, month, account_id=account_id, include_transfers=include_transfers
            )
            lookback = AVERAGE_LOOKBACK_MONTHS
            source_months, averages = category_spend_averages(
                db,
                user,
                month,
                lookback=lookback,
                account_id=account_id,
                include_transfers=include_transfers,
            )
            categories = spending_by_category(
                db,
                user,
                month,
                account_id=account_id,
                include_transfers=include_transfers,
            )
            for row in categories:
                avg = int(averages.get(row.get("category_id"), 0))
                row["average_spend_cents"] = avg
                row["suggested_limit_cents"] = avg
            return {
                "month": month,
                "categories": categories,
                **{k: cashflow[k] for k in (
                    "income_cents",
                    "gross_spend_cents",
                    "reimbursement_in_cents",
                    "net_spend_cents",
                    "personal_spend_cents",
                    "unclassified_count",
                    "unclassified_outflow_cents",
                    "incomplete",
                )},
                "income_target_cents": get_income_target(db, user, month),
                "average_lookback_months": lookback,
                "average_source_months": source_months,
            }
        finally:
            db.close()

    @router.put("/budgets")
    def set_budget(request: Request, body: BudgetSet):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            _require_owned_category(db, user, body.category_id)
            upsert_budget_for_owner(
                db,
                user,
                category_id=body.category_id,
                month=body.month,
                limit_cents=body.limit_cents,
            )
            return {"ok": True}
        finally:
            db.close()

    @router.post("/budgets/copy")
    def copy_budgets(request: Request, body: BudgetCopyBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return copy_budgets_for_owner(db, user, body.from_month, body.to_month)
        finally:
            db.close()

    @router.put("/budgets/income-target")
    def put_income_target(request: Request, body: IncomeTargetBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            row = set_income_target(db, user, body.month, body.income_target_cents)
            return {"month": row.month, "income_target_cents": row.income_target_cents}
        finally:
            db.close()

    @router.get("/planned")
    def list_planned(request: Request):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return {"planned": [planned_dict(p) for p in list_planned_for_owner(db, user)]}
        finally:
            db.close()

    @router.post("/planned")
    def create_planned(request: Request, body: PlannedCreate):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            row = create_planned_for_owner(
                db,
                user,
                name=body.name,
                kind=body.kind,
                amount_cents=body.amount_cents,
                include_in_job_overlay=body.include_in_job_overlay,
                is_funding=body.is_funding,
                notes=body.notes,
                starts_on=body.starts_on,
            )
            return planned_dict(row)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            db.close()

    @router.delete("/planned/{planned_id}")
    def delete_planned(request: Request, planned_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                delete_planned_for_owner(db, user, planned_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {"ok": True}
        finally:
            db.close()

    @router.get("/job-scenario")
    def get_job(request: Request, include_business: bool = True, month: Optional[str] = None):
        user = require_finance_user(request)
        month = _optional_month(month)
        db = get_session_factory()()
        try:
            overlay = job_overlay(db, user, include_business=include_business, month=month)
            scenario = get_job_scenario(db, user)
            return {
                "take_home_cents": scenario.take_home_cents if scenario else 0,
                "label": scenario.label if scenario else overlay["label"],
                **overlay,
            }
        finally:
            db.close()

    @router.put("/job-scenario")
    def put_job(request: Request, body: JobScenarioBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            row = upsert_job_scenario(db, user, take_home_cents=body.take_home_cents, label=body.label)
            overlay = job_overlay(db, user)
            return {
                "id": row.id,
                "take_home_cents": row.take_home_cents,
                "label": row.label,
                **overlay,
            }
        finally:
            db.close()

    @router.get("/reports/spending")
    def report_spending(
        request: Request,
        month: Optional[str] = None,
        account_id: Optional[str] = None,
        include_transfers: bool = False,
    ):
        user = require_finance_user(request)
        month = _optional_month(month) or month_key(date.today())
        db = get_session_factory()()
        try:
            cashflow = month_cashflow(
                db, user, month, account_id=account_id, include_transfers=include_transfers
            )
            return {
                "month": month,
                "categories": spending_by_category(
                    db,
                    user,
                    month,
                    account_id=account_id,
                    include_transfers=include_transfers,
                ),
                **cashflow,
                **month_review(db, user, month, account_id=account_id),
            }
        finally:
            db.close()

    @router.get("/reports/trends")
    def report_trends(
        request: Request,
        months: int = Query(6, ge=1, le=24),
        include_transfers: bool = False,
        account_id: Optional[str] = None,
    ):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return {
                "trends": monthly_trends(
                    db, user, months, include_transfers=include_transfers, account_id=account_id
                )
            }
        finally:
            db.close()

    @router.get("/reports/cashflow")
    def report_cashflow(
        request: Request,
        month: Optional[str] = None,
        account_id: Optional[str] = None,
        include_transfers: bool = False,
    ):
        user = require_finance_user(request)
        month = _optional_month(month) or month_key(date.today())
        db = get_session_factory()()
        try:
            return month_cashflow(
                db, user, month, account_id=account_id, include_transfers=include_transfers
            )
        finally:
            db.close()

    @router.get("/reports/spend-by-account")
    def report_spend_by_account(request: Request, month: Optional[str] = None):
        user = require_finance_user(request)
        month = _optional_month(month) or month_key(date.today())
        db = get_session_factory()()
        try:
            return {"month": month, "accounts": spend_by_account(db, user, month)}
        finally:
            db.close()

    @router.get("/reports/net-worth")
    def report_net_worth(request: Request):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return net_worth(db, user)
        finally:
            db.close()

    @router.get("/recurring")
    def list_recurring(request: Request):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return {"series": list_recurring_series(db, user)}
        finally:
            db.close()

    @router.patch("/recurring/{series_id}")
    def patch_recurring(request: Request, series_id: str, body: RecurringPatch):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                row = patch_recurring_series(
                    db,
                    user,
                    series_id,
                    status=body.status,
                    category_id=body.category_id,
                    movement_class=body.movement_class,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"id": row.id, "status": row.status}
        finally:
            db.close()

    @router.get("/movements/candidates")
    def get_movement_candidates(
        request: Request,
        tx_id: str,
        day_gap: Optional[int] = None,
    ):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                return {"candidates": movement_candidates(db, user, tx_id, day_gap=day_gap)}
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
        finally:
            db.close()

    @router.post("/movements/detect")
    def post_detect_movements(request: Request, body: MovementDetectBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            from_date = date.fromisoformat(body.from_date) if body.from_date else None
            to_date = date.fromisoformat(body.to_date) if body.to_date else None
            return detect_movements(
                db,
                user,
                account_ids=body.account_ids,
                day_gap=body.day_gap,
                auto_link=body.auto_link,
                from_date=from_date,
                to_date=to_date,
            )
        finally:
            db.close()

    @router.post("/movements/link")
    def post_link_movements(request: Request, body: MovementLinkBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                group_id = link_movements(db, user, body.tx_ids)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"movement_group_id": group_id}
        finally:
            db.close()

    @router.post("/movements/unlink")
    def post_unlink_movements(request: Request, body: MovementUnlinkBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                cleared = unlink_movement(
                    db, user, tx_id=body.tx_id, movement_group_id=body.movement_group_id
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, "cleared": cleared}
        finally:
            db.close()

    @router.post("/transactions/bulk")
    def bulk_classify(request: Request, body: BulkClassifyBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            if body.category_id:
                _require_owned_category(db, user, body.category_id)
            try:
                updated = bulk_classify_transactions(
                    db,
                    user,
                    tx_ids=body.transaction_ids,
                    movement_class=body.movement_class,
                    category_id=body.category_id,
                    apply_to_payee=body.apply_to_payee,
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, "updated": updated}
        finally:
            db.close()

    @router.post("/transactions/{tx_id}/classify")
    def classify_tx(request: Request, tx_id: str, body: MovementClassifyBody):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                tx = classify_transaction(db, user, tx_id, body.movement_class)
            except ValueError as exc:
                message = str(exc)
                code = 404 if "not found" in message.lower() else 400
                raise HTTPException(code, message) from exc
            return _transaction_dict(tx)
        finally:
            db.close()

    from integrations.finance.routes_goals import mount_goals
    from integrations.finance.routes_investing import mount_investing
    from integrations.finance.routes_sankey import mount_sankey

    mount_goals(router)
    mount_investing(router)
    mount_sankey(router)
    return router
