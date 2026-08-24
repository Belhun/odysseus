"""Mount GET /reports/sankey on the finance router."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from integrations.finance.database import get_session_factory
from integrations.finance.services.sankey import month_sankey


def mount_sankey(router: APIRouter) -> None:
    from datetime import date

    from integrations.finance.routes import _optional_month, require_finance_user
    from integrations.finance.services.reports import month_key

    @router.get("/reports/sankey")
    def get_sankey(request: Request, month: Optional[str] = None):
        user = require_finance_user(request)
        month = _optional_month(month) or month_key(date.today())
        db = get_session_factory()()
        try:
            return month_sankey(db, user, month)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        finally:
            db.close()
