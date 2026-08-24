"""PhoneApp chat routes — scope-aware list/create on the existing session store.

Does not replace ``routes/chat_routes.py``. Send/history/stop stay on the
stock chat and history APIs. Identity is ``effective_user`` so an ``ody_``
token owner sees the same chats as the web sidebar.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request

from core.database import ModelEndpoint, Session as DbSession, SessionLocal
from src.auth_helpers import owner_filter
from src.chat_token_auth import require_chat_user
from src.endpoint_resolver import (
    _endpoint_cached_models,
    _first_chat_model,
    build_chat_url,
    build_headers,
)

logger = logging.getLogger(__name__)

_HIDDEN_SYSTEM_SESSION_NAMES = {
    "[Task] Chat Sessions Tidy",
    "[Task] Documents Tidy",
    "[Task] Memory Tidy",
    "[Task] Research Tidy",
    "[Task] Email Mark Boundaries",
    "[Task] Email Tags",
    "[Task] Skills Audit",
}


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _persist_session_headers(session_id: str, headers: dict | None) -> None:
    db = SessionLocal()
    try:
        row = db.query(DbSession).filter(DbSession.id == session_id).first()
        if row is not None:
            row.headers = headers or {}
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("mobile chat: persist headers failed")
    finally:
        db.close()


def pick_default_llm(owner: str) -> Optional[tuple[str, str, dict]]:
    """First enabled LLM the owner can use: (chat_url, model_id, headers)."""
    db = SessionLocal()
    try:
        q = db.query(ModelEndpoint).filter(
            ModelEndpoint.is_enabled == True,  # noqa: E712
            (ModelEndpoint.model_type == "llm") | (ModelEndpoint.model_type == None),  # noqa: E711
        )
        if owner:
            q = q.filter((ModelEndpoint.owner == owner) | (ModelEndpoint.owner == None))  # noqa: E711
        for ep in q.all():
            if owner and ep.owner not in (None, owner):
                continue
            try:
                hidden = set(json.loads(ep.hidden_models) if ep.hidden_models else [])
            except (ValueError, TypeError):
                hidden = set()
            model_ids = [m for m in _endpoint_cached_models(ep) if m not in hidden]
            model = _first_chat_model(model_ids)
            if not model:
                continue
            try:
                chat_url = build_chat_url(ep.base_url)
            except Exception:
                chat_url = ep.base_url
            headers = build_headers(ep.api_key, ep.base_url or chat_url)
            return chat_url, str(model), headers or {}
    except Exception:
        logger.exception("mobile chat: default model lookup failed")
        return None
    finally:
        db.close()
    return None


def setup_chat_mobile_routes(session_manager) -> APIRouter:
    router = APIRouter(tags=["chat_mobile"])

    @router.get("/api/mobile/chat/sessions")
    def list_sessions(request: Request) -> dict:
        user = require_chat_user(request)
        memory = session_manager.get_sessions_for_user(user if user else None)
        meta: dict[str, DbSession] = {}
        db = SessionLocal()
        try:
            q = db.query(DbSession).filter(DbSession.archived == False)  # noqa: E712
            q = owner_filter(q, DbSession, user)
            meta = {row.id: row for row in q.all()}
        except Exception:
            logger.debug("mobile chat: session meta lookup skipped", exc_info=True)
        finally:
            db.close()

        sessions = []
        for sess in memory.values():
            if getattr(sess, "archived", False):
                continue
            name = (getattr(sess, "name", None) or "").strip()
            if name in ("Nobody", "Incognito"):
                continue
            if name in _HIDDEN_SYSTEM_SESSION_NAMES:
                continue
            row = meta.get(sess.id)
            history = getattr(sess, "history", None) or []
            sessions.append({
                "id": sess.id,
                "name": getattr(sess, "name", None) or "Chat",
                "model": getattr(sess, "model", None) or (row.model if row else ""),
                "updated_at": _iso(getattr(row, "updated_at", None)),
                "last_message_at": _iso(getattr(row, "last_message_at", None)),
                "message_count": getattr(sess, "message_count", None)
                or (row.message_count if row else None)
                or len(history),
            })
        sessions.sort(
            key=lambda item: item.get("last_message_at") or item.get("updated_at") or "",
            reverse=True,
        )
        return {"sessions": sessions}

    @router.post("/api/mobile/chat/sessions")
    async def create_session(request: Request) -> dict:
        user = require_chat_user(request)
        name = "Phone"
        try:
            body = await request.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            raw_name = str(body.get("name") or "").strip()
            if raw_name:
                name = raw_name[:80]

        picked = pick_default_llm(user)
        if picked is None:
            raise HTTPException(400, "No models configured")
        endpoint_url, model, headers = picked
        sid = str(uuid.uuid4())
        session_manager.create_session(
            session_id=sid,
            name=name,
            endpoint_url=endpoint_url,
            model=model,
            owner=user or None,
        )
        try:
            live = session_manager.sessions.get(sid)
            if live is not None and headers:
                live.headers = headers
            if headers:
                _persist_session_headers(sid, headers)
        except Exception:
            logger.debug("mobile chat: header attach skipped", exc_info=True)
        return {"id": sid, "name": name, "model": model}

    return router
