"""manage_archive tool — ingest/get/list raw conversation archive items."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

from src.tools._common import _parse_tool_args
from services.dossier import access
from services.dossier.archive_search import search_archive

logger = logging.getLogger(__name__)


def _parse_captured_at(raw) -> Optional[datetime]:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt
    except ValueError:
        return None


async def do_manage_archive(content: str, owner: Optional[str] = None) -> Dict:
    """Handle manage_archive: ingest, get, list, search."""
    from core.database import SessionLocal

    if not owner:
        return {"error": "owner required", "exit_code": 1}
    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = (args.get("action") or "").replace("-", "_").strip().lower()
    db = SessionLocal()
    try:
        if action == "ingest":
            try:
                item = access.create_archive_item(
                    db,
                    owner=owner,
                    source_tool=args.get("source_tool"),
                    body=args.get("body") or "",
                    external_id=args.get("external_id"),
                    locator=args.get("locator"),
                    captured_at=_parse_captured_at(args.get("captured_at")),
                    person_id=args.get("person_id"),
                    situation_id=args.get("situation_id"),
                    content_hash=args.get("content_hash"),
                )
                person_id = item.person_id
                if person_id:
                    access.add_timeline_event(
                        db,
                        owner=owner,
                        person_id=person_id,
                        situation_id=item.situation_id,
                        event_type="archive_ingest",
                        summary=f"Archived from {item.source_tool}",
                        ref_kind="archive",
                        ref_id=item.id,
                    )
                db.commit()
                return {"ok": True, "item": access.archive_to_dict(item)}
            except (ValueError, LookupError) as e:
                db.rollback()
                return {"error": str(e), "exit_code": 1}

        if action == "get":
            item_id = (args.get("id") or args.get("item_id") or "").strip()
            if not item_id:
                return {"error": "id required", "exit_code": 1}
            item = access.get_archive_item(db, item_id, owner)
            if not item:
                return {"error": "not found", "exit_code": 1}
            return {"ok": True, "item": access.archive_to_dict(item)}

        if action == "list":
            from core.database import DossierArchiveItem

            q = db.query(DossierArchiveItem).filter(DossierArchiveItem.owner == owner)
            if args.get("person_id"):
                q = q.filter(DossierArchiveItem.person_id == args["person_id"])
            if args.get("situation_id"):
                q = q.filter(DossierArchiveItem.situation_id == args["situation_id"])
            rows = q.order_by(DossierArchiveItem.captured_at.desc()).limit(
                min(int(args.get("limit") or 50), 100)
            ).all()
            return {"ok": True, "items": [access.archive_to_dict(r) for r in rows]}

        if action == "search":
            query = (args.get("query") or "").strip()
            if not query:
                return {"error": "query required", "exit_code": 1}
            hits = search_archive(
                query,
                owner=owner,
                db=db,
                person_id=args.get("person_id"),
                situation_id=args.get("situation_id"),
                limit=int(args.get("limit") or 10),
            )
            return {
                "ok": True,
                "hits": [
                    {
                        "id": h.item_id,
                        "source_tool": h.source_tool,
                        "external_id": h.external_id,
                        "locator": h.locator,
                        "snippet": h.snippet,
                        "person_id": h.person_id,
                        "situation_id": h.situation_id,
                        "captured_at": h.captured_at,
                        "open_ref": f"#archive-{h.item_id}",
                    }
                    for h in hits
                ],
            }

        return {
            "error": f"Unknown action '{action}'. Use ingest, get, list, or search.",
            "exit_code": 1,
        }
    except Exception as e:
        logger.exception("manage_archive failed")
        db.rollback()
        return {"error": str(e), "exit_code": 1}
    finally:
        db.close()
