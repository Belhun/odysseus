"""Investing HTTP routes. Mount onto the finance APIRouter."""

from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from integrations.finance.database import get_session_factory
from integrations.finance.routes import require_finance_user
from integrations.finance.services.investing import (
    asset_dict,
    create_asset_for_owner,
    delete_asset_for_owner,
    get_asset_for_owner,
    list_assets_for_owner,
    list_valuations_for_owner,
    patch_asset_for_owner,
    summary_for_owner,
    update_asset_value_for_owner,
    valuation_dict,
)


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    symbol: str = ""
    asset_kind: str = "other"
    account_id: Optional[str] = None
    shares_millishares: Optional[int] = None
    shares: Optional[Union[str, float, int]] = None
    cost_basis_cents: int = 0
    current_value_cents: int = 0
    notes: str = ""


class AssetPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    symbol: Optional[str] = None
    asset_kind: Optional[str] = None
    account_id: Optional[str] = None
    clear_account: bool = False
    shares_millishares: Optional[int] = None
    shares: Optional[Union[str, float, int]] = None
    cost_basis_cents: Optional[int] = None
    current_value_cents: Optional[int] = None
    notes: Optional[str] = None
    archived: Optional[bool] = None


class AssetValueUpdate(BaseModel):
    current_value_cents: int
    as_of: Optional[str] = None
    shares_millishares: Optional[int] = None
    shares: Optional[Union[str, float, int]] = None


def _http_value_error(exc: ValueError) -> HTTPException:
    return HTTPException(400, str(exc))


def mount_investing(router: APIRouter) -> None:
    @router.get("/invest/summary")
    def invest_summary(request: Request):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            return summary_for_owner(db, user)
        finally:
            db.close()

    @router.get("/invest/assets")
    def list_invest_assets(
        request: Request,
        include_archived: bool = False,
        asset_kind: Optional[str] = None,
    ):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                rows = list_assets_for_owner(
                    db, user, include_archived=include_archived, asset_kind=asset_kind
                )
            except ValueError as exc:
                raise _http_value_error(exc) from exc
            return {"assets": [asset_dict(row) for row in rows]}
        finally:
            db.close()

    @router.post("/invest/assets")
    def create_invest_asset(request: Request, body: AssetCreate):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                asset = create_asset_for_owner(
                    db,
                    user,
                    name=body.name,
                    symbol=body.symbol,
                    asset_kind=body.asset_kind,
                    account_id=body.account_id,
                    shares_millishares=body.shares_millishares,
                    shares=body.shares,
                    cost_basis_cents=body.cost_basis_cents,
                    current_value_cents=body.current_value_cents,
                    notes=body.notes,
                )
            except ValueError as exc:
                raise _http_value_error(exc) from exc
            return asset_dict(asset)
        finally:
            db.close()

    @router.get("/invest/assets/{asset_id}")
    def get_invest_asset(request: Request, asset_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            asset = get_asset_for_owner(db, user, asset_id)
            if not asset:
                raise HTTPException(404, "Holding not found")
            return asset_dict(asset)
        finally:
            db.close()

    @router.patch("/invest/assets/{asset_id}")
    def patch_invest_asset(request: Request, asset_id: str, body: AssetPatch):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                asset = patch_asset_for_owner(
                    db,
                    user,
                    asset_id,
                    name=body.name,
                    symbol=body.symbol,
                    asset_kind=body.asset_kind,
                    account_id=body.account_id,
                    clear_account=body.clear_account,
                    shares_millishares=body.shares_millishares,
                    shares=body.shares,
                    cost_basis_cents=body.cost_basis_cents,
                    current_value_cents=body.current_value_cents,
                    notes=body.notes,
                    archived=body.archived,
                )
            except ValueError as exc:
                raise _http_value_error(exc) from exc
            if not asset:
                raise HTTPException(404, "Holding not found")
            return asset_dict(asset)
        finally:
            db.close()

    @router.delete("/invest/assets/{asset_id}")
    def delete_invest_asset(request: Request, asset_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            ok = delete_asset_for_owner(db, user, asset_id)
            if not ok:
                raise HTTPException(404, "Holding not found")
            return {"ok": True}
        finally:
            db.close()

    @router.post("/invest/assets/{asset_id}/value")
    def post_invest_asset_value(request: Request, asset_id: str, body: AssetValueUpdate):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            try:
                asset = update_asset_value_for_owner(
                    db,
                    user,
                    asset_id,
                    current_value_cents=body.current_value_cents,
                    as_of=body.as_of,
                    shares_millishares=body.shares_millishares,
                    shares=body.shares,
                )
            except ValueError as exc:
                raise _http_value_error(exc) from exc
            if not asset:
                raise HTTPException(404, "Holding not found")
            return asset_dict(asset)
        finally:
            db.close()

    @router.get("/invest/assets/{asset_id}/valuations")
    def get_invest_asset_valuations(request: Request, asset_id: str):
        user = require_finance_user(request)
        db = get_session_factory()()
        try:
            rows = list_valuations_for_owner(db, user, asset_id)
            if rows is None:
                raise HTTPException(404, "Holding not found")
            return {"valuations": [valuation_dict(row) for row in rows]}
        finally:
            db.close()
