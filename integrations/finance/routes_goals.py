"""Mount Goals CRUD on the finance router."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from integrations.finance.services.goals import (
    create_goal,
    delete_goal,
    ensure_goals_schema,
    get_goal,
    goal_dict,
    list_goals,
    patch_goal,
)


class GoalCreate(BaseModel):
    name: str = Field(min_length=1)
    kind: str = "account"
    target_cents: int = 0
    target_date: Optional[str] = None
    account_id: Optional[str] = None
    category_id: Optional[str] = None
    baseline_cents: int = 0
    icon: Optional[str] = None
    color: str = "#5b8abf"


class GoalPatch(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    target_cents: Optional[int] = None
    target_date: Optional[str] = None
    account_id: Optional[str] = None
    category_id: Optional[str] = None
    baseline_cents: Optional[int] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    archived: Optional[bool] = None


def mount_goals(router: APIRouter) -> None:
    from integrations.finance import routes as finance_routes

    try:
        from integrations.finance.database import get_engine

        ensure_goals_schema(get_engine())
    except Exception:
        pass

    @router.get("/goals")
    def get_goals(request: Request, include_archived: bool = False):
        user = finance_routes.require_finance_user(request)
        db = finance_routes.get_session_factory()()
        try:
            return {"goals": list_goals(db, user, include_archived=include_archived)}
        finally:
            db.close()

    @router.post("/goals")
    def post_goal(request: Request, body: GoalCreate):
        user = finance_routes.require_finance_user(request)
        db = finance_routes.get_session_factory()()
        try:
            try:
                goal = create_goal(db, user, body.model_dump())
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return goal_dict(db, goal)
        finally:
            db.close()

    @router.get("/goals/{goal_id}")
    def get_one(request: Request, goal_id: str):
        user = finance_routes.require_finance_user(request)
        db = finance_routes.get_session_factory()()
        try:
            goal = get_goal(db, user, goal_id)
            if goal is None:
                raise HTTPException(404, "goal not found")
            return goal_dict(db, goal)
        finally:
            db.close()

    @router.patch("/goals/{goal_id}")
    def patch_one(request: Request, goal_id: str, body: GoalPatch):
        user = finance_routes.require_finance_user(request)
        db = finance_routes.get_session_factory()()
        try:
            try:
                goal = patch_goal(db, user, goal_id, body.model_dump(exclude_unset=True))
            except ValueError as exc:
                code = 404 if "not found" in str(exc) else 400
                raise HTTPException(code, str(exc)) from exc
            return goal_dict(db, goal)
        finally:
            db.close()

    @router.delete("/goals/{goal_id}")
    def delete_one(request: Request, goal_id: str):
        user = finance_routes.require_finance_user(request)
        db = finance_routes.get_session_factory()()
        try:
            try:
                delete_goal(db, user, goal_id)
            except ValueError as exc:
                raise HTTPException(404, str(exc)) from exc
            return {"ok": True}
        finally:
            db.close()
