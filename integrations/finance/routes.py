"""Finance routes — accounts, import, transactions, budgets, reports."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from integrations.finance.database import get_session_factory
from integrations.finance.models import (
    FinanceAccount,
    FinanceCategory,
    FinanceCategoryBudget,
    FinanceCategorizationRule,
    FinanceImportBatch,
    FinanceTransaction,
)
from integrations.finance.services.categories import ensure_default_categories
from integrations.finance.services.import_service import (
    account_balance_cents,
    build_import_preview,
    commit_import_preview,
)
from integrations.finance.services.reports import month_key, monthly_trends, spending_by_category
from src.auth_helpers import require_user
from src.upload_limits import FINANCE_IMPORT_MAX_BYTES, read_upload_limited

ACCOUNT_TYPES = ("checking", "savings", "credit_card", "loan", "cash", "other")


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    institution: str = ""
    account_type: str = "checking"
    currency: str = "USD"
    mask_last4: Optional[str] = None
    opening_balance_cents: int = 0
    opening_balance_date: Optional[str] = None
    credit_limit_cents: Optional[int] = None


class AccountPatch(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    account_type: Optional[str] = None
    mask_last4: Optional[str] = None
    opening_balance_cents: Optional[int] = None
    opening_balance_date: Optional[str] = None
    credit_limit_cents: Optional[int] = None
    is_closed: Optional[bool] = None
    display_order: Optional[int] = None


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    parent_id: Optional[str] = None
    is_income: bool = False
    color: str = "#5b8abf"


class RuleCreate(BaseModel):
    pattern: str = Field(min_length=1, max_length=200)
    category_id: str
    priority: int = 0


class BudgetSet(BaseModel):
    category_id: str
    month: str
    limit_cents: int = Field(ge=0)


class TransactionPatch(BaseModel):
    category_id: Optional[str] = None
    payee: Optional[str] = None
    memo: Optional[str] = None
    status: Optional[str] = None


class ImportCommitBody(BaseModel):
    preview_id: str
    skip_duplicates: bool = True


def _parse_optional_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    return datetime.strptime(raw[:10], "%Y-%m-%d").date()


def _require_owned_category(db, user: str, category_id: str | None) -> None:
    if not category_id:
        return
    cat = db.query(FinanceCategory).filter(
        FinanceCategory.id == category_id,
        FinanceCategory.owner == user,
    ).first()
    if not cat:
        raise HTTPException(404, "Category not found")


def _account_dict(db, account: FinanceAccount) -> dict[str, Any]:
    balance = account_balance_cents(db, account)
    return {
        "id": account.id,
        "name": account.name,
        "institution": account.institution or "",
        "account_type": account.account_type,
        "currency": account.currency,
        "mask_last4": account.mask_last4,
        "opening_balance_cents": account.opening_balance_cents or 0,
        "opening_balance_date": account.opening_balance_date.isoformat() if account.opening_balance_date else None,
        "credit_limit_cents": account.credit_limit_cents,
        "is_closed": bool(account.is_closed),
        "display_order": account.display_order or 0,
        "balance_cents": balance,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def _transaction_dict(tx: FinanceTransaction, category_name: str | None = None) -> dict[str, Any]:
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
        "bank_category": tx.bank_category,
        "import_batch_id": tx.import_batch_id,
    }


def setup_finance_routes() -> APIRouter:
    router = APIRouter(prefix="/api/finance", tags=["finance"])

    @router.get("/accounts")
    def list_accounts(request: Request, include_closed: bool = False):
        user = require_user(request)
        db = get_session_factory()()
        try:
            ensure_default_categories(db, user)
            q = db.query(FinanceAccount).filter(FinanceAccount.owner == user)
            if not include_closed:
                q = q.filter(FinanceAccount.is_closed == False)  # noqa: E712
            accounts = q.order_by(FinanceAccount.display_order, FinanceAccount.name).all()
            return {"accounts": [_account_dict(db, a) for a in accounts]}
        finally:
            db.close()

    @router.post("/accounts")
    def create_account(request: Request, body: AccountCreate):
        user = require_user(request)
        if body.account_type not in ACCOUNT_TYPES:
            raise HTTPException(400, f"account_type must be one of: {', '.join(ACCOUNT_TYPES)}")
        db = get_session_factory()()
        try:
            account = FinanceAccount(
                id=str(uuid.uuid4()),
                owner=user,
                name=body.name.strip(),
                institution=(body.institution or "").strip(),
                account_type=body.account_type,
                currency=body.currency or "USD",
                mask_last4=body.mask_last4,
                opening_balance_cents=body.opening_balance_cents,
                opening_balance_date=_parse_optional_date(body.opening_balance_date),
                credit_limit_cents=body.credit_limit_cents,
            )
            db.add(account)
            db.commit()
            return _account_dict(db, account)
        finally:
            db.close()

    @router.patch("/accounts/{account_id}")
    def patch_account(request: Request, account_id: str, body: AccountPatch):
        user = require_user(request)
        db = get_session_factory()()
        try:
            account = db.query(FinanceAccount).filter(
                FinanceAccount.id == account_id, FinanceAccount.owner == user
            ).first()
            if not account:
                raise HTTPException(404, "Account not found")
            for field in ("name", "institution", "account_type", "mask_last4", "is_closed", "display_order"):
                val = getattr(body, field)
                if val is not None:
                    setattr(account, field, val)
            if body.opening_balance_cents is not None:
                account.opening_balance_cents = body.opening_balance_cents
            if body.opening_balance_date is not None:
                account.opening_balance_date = _parse_optional_date(body.opening_balance_date)
            if body.credit_limit_cents is not None:
                account.credit_limit_cents = body.credit_limit_cents
            db.commit()
            return _account_dict(db, account)
        finally:
            db.close()

    @router.delete("/accounts/{account_id}")
    def delete_account(request: Request, account_id: str):
        user = require_user(request)
        db = get_session_factory()()
        try:
            account = db.query(FinanceAccount).filter(
                FinanceAccount.id == account_id, FinanceAccount.owner == user
            ).first()
            if not account:
                raise HTTPException(404, "Account not found")
            tx_count = db.query(FinanceTransaction).filter(
                FinanceTransaction.account_id == account_id
            ).count()
            if tx_count:
                raise HTTPException(400, f"Account has {tx_count} transactions; delete batches first or close account")
            db.delete(account)
            db.commit()
            return {"ok": True}
        finally:
            db.close()

    @router.get("/categories")
    def list_categories(request: Request):
        user = require_user(request)
        db = get_session_factory()()
        try:
            ensure_default_categories(db, user)
            cats = (
                db.query(FinanceCategory)
                .filter(FinanceCategory.owner == user)
                .order_by(FinanceCategory.display_order, FinanceCategory.name)
                .all()
            )
            return {
                "categories": [
                    {
                        "id": c.id,
                        "name": c.name,
                        "parent_id": c.parent_id,
                        "is_income": bool(c.is_income),
                        "color": c.color,
                    }
                    for c in cats
                ]
            }
        finally:
            db.close()

    @router.post("/categories")
    def create_category(request: Request, body: CategoryCreate):
        user = require_user(request)
        db = get_session_factory()()
        try:
            _require_owned_category(db, user, body.parent_id)
            cat = FinanceCategory(
                id=str(uuid.uuid4()),
                owner=user,
                name=body.name.strip(),
                parent_id=body.parent_id,
                is_income=body.is_income,
                color=body.color,
            )
            db.add(cat)
            db.commit()
            return {"id": cat.id, "name": cat.name}
        finally:
            db.close()

    @router.get("/rules")
    def list_rules(request: Request):
        user = require_user(request)
        db = get_session_factory()()
        try:
            rules = (
                db.query(FinanceCategorizationRule)
                .filter(FinanceCategorizationRule.owner == user)
                .order_by(FinanceCategorizationRule.priority.desc())
                .all()
            )
            return {
                "rules": [
                    {
                        "id": r.id,
                        "pattern": r.pattern,
                        "category_id": r.category_id,
                        "priority": r.priority,
                    }
                    for r in rules
                ]
            }
        finally:
            db.close()

    @router.post("/rules")
    def create_rule(request: Request, body: RuleCreate):
        user = require_user(request)
        db = get_session_factory()()
        try:
            _require_owned_category(db, user, body.category_id)
            rule = FinanceCategorizationRule(
                id=str(uuid.uuid4()),
                owner=user,
                pattern=body.pattern.strip(),
                category_id=body.category_id,
                priority=body.priority,
            )
            db.add(rule)
            db.commit()
            return {"id": rule.id}
        finally:
            db.close()

    @router.delete("/rules/{rule_id}")
    def delete_rule(request: Request, rule_id: str):
        user = require_user(request)
        db = get_session_factory()()
        try:
            rule = db.query(FinanceCategorizationRule).filter(
                FinanceCategorizationRule.id == rule_id,
                FinanceCategorizationRule.owner == user,
            ).first()
            if not rule:
                raise HTTPException(404, "Rule not found")
            db.delete(rule)
            db.commit()
            return {"ok": True}
        finally:
            db.close()

    @router.get("/transactions")
    def list_transactions(
        request: Request,
        account_id: Optional[str] = None,
        search: str = "",
        category_id: Optional[str] = None,
        month: Optional[str] = None,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        user = require_user(request)
        db = get_session_factory()()
        try:
            q = db.query(FinanceTransaction).filter(FinanceTransaction.owner == user)
            if account_id:
                q = q.filter(FinanceTransaction.account_id == account_id)
            if category_id:
                q = q.filter(FinanceTransaction.category_id == category_id)
            if month:
                from integrations.finance.services.reports import month_bounds
                start, end = month_bounds(month)
                q = q.filter(FinanceTransaction.date >= start, FinanceTransaction.date <= end)
            if search.strip():
                like = f"%{search.strip()}%"
                q = q.filter(FinanceTransaction.payee.ilike(like))
            total = q.count()
            txs = q.order_by(FinanceTransaction.date.desc(), FinanceTransaction.created_at.desc()).offset(offset).limit(limit).all()
            cat_map = {
                c.id: c.name
                for c in db.query(FinanceCategory).filter(FinanceCategory.owner == user).all()
            }
            return {
                "total": total,
                "transactions": [_transaction_dict(tx, cat_map.get(tx.category_id)) for tx in txs],
            }
        finally:
            db.close()

    @router.patch("/transactions/{tx_id}")
    def patch_transaction(request: Request, tx_id: str, body: TransactionPatch):
        user = require_user(request)
        db = get_session_factory()()
        try:
            tx = db.query(FinanceTransaction).filter(
                FinanceTransaction.id == tx_id, FinanceTransaction.owner == user
            ).first()
            if not tx:
                raise HTTPException(404, "Transaction not found")
            if body.category_id is not None:
                if body.category_id:
                    _require_owned_category(db, user, body.category_id)
                tx.category_id = body.category_id or None
            if body.payee is not None:
                tx.payee = body.payee[:500]
            if body.memo is not None:
                tx.memo = body.memo[:1000]
            if body.status is not None:
                tx.status = body.status
            db.commit()
            return _transaction_dict(tx)
        finally:
            db.close()

    @router.post("/import/preview")
    async def import_preview(
        request: Request,
        file: UploadFile = File(...),
        account_id: str = Form(...),
        preset: str = Form(""),
    ):
        user = require_user(request)
        content = await read_upload_limited(file, FINANCE_IMPORT_MAX_BYTES, "Finance import")
        db = get_session_factory()()
        try:
            result = build_import_preview(
                db,
                user,
                account_id,
                file.filename or "import.csv",
                content,
                preset=preset or None,
            )
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            db.close()

    @router.post("/import/commit")
    def import_commit(request: Request, body: ImportCommitBody):
        user = require_user(request)
        db = get_session_factory()()
        try:
            result = commit_import_preview(
                db, user, body.preview_id, skip_duplicates=body.skip_duplicates
            )
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            db.close()

    @router.get("/import/batches")
    def list_batches(request: Request, account_id: Optional[str] = None):
        user = require_user(request)
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
        user = require_user(request)
        db = get_session_factory()()
        try:
            batch = db.query(FinanceImportBatch).filter(
                FinanceImportBatch.id == batch_id, FinanceImportBatch.owner == user
            ).first()
            if not batch:
                raise HTTPException(404, "Import batch not found")
            deleted = (
                db.query(FinanceTransaction)
                .filter(FinanceTransaction.import_batch_id == batch_id)
                .delete(synchronize_session=False)
            )
            db.delete(batch)
            db.commit()
            return {"ok": True, "deleted_transactions": deleted}
        finally:
            db.close()

    @router.get("/budgets")
    def list_budgets(request: Request, month: Optional[str] = None):
        user = require_user(request)
        month = month or month_key(date.today())
        db = get_session_factory()()
        try:
            ensure_default_categories(db, user)
            return {"month": month, "categories": spending_by_category(db, user, month)}
        finally:
            db.close()

    @router.put("/budgets")
    def set_budget(request: Request, body: BudgetSet):
        user = require_user(request)
        db = get_session_factory()()
        try:
            _require_owned_category(db, user, body.category_id)
            existing = db.query(FinanceCategoryBudget).filter(
                FinanceCategoryBudget.owner == user,
                FinanceCategoryBudget.month == body.month,
                FinanceCategoryBudget.category_id == body.category_id,
            ).first()
            if existing:
                existing.limit_cents = body.limit_cents
            else:
                db.add(FinanceCategoryBudget(
                    id=str(uuid.uuid4()),
                    owner=user,
                    category_id=body.category_id,
                    month=body.month,
                    limit_cents=body.limit_cents,
                ))
            db.commit()
            return {"ok": True}
        finally:
            db.close()

    @router.get("/reports/spending")
    def report_spending(request: Request, month: Optional[str] = None):
        user = require_user(request)
        month = month or month_key(date.today())
        db = get_session_factory()()
        try:
            return {"month": month, "categories": spending_by_category(db, user, month)}
        finally:
            db.close()

    @router.get("/reports/trends")
    def report_trends(request: Request, months: int = Query(6, ge=1, le=24)):
        user = require_user(request)
        db = get_session_factory()()
        try:
            return {"trends": monthly_trends(db, user, months)}
        finally:
            db.close()

    return router
