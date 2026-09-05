"""FTS5 search over dossier archive items."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import DossierArchiveItem
from src.session_search import _sanitize_fts_query

logger = logging.getLogger(__name__)


@dataclass
class ArchiveSearchHit:
    item_id: str
    source_tool: str
    external_id: Optional[str]
    locator: Optional[str]
    snippet: str
    person_id: Optional[str]
    situation_id: Optional[str]
    captured_at: Optional[str]


def _has_archive_fts(db: Session) -> bool:
    try:
        bind = db.get_bind()
        if getattr(getattr(bind, "dialect", None), "name", None) != "sqlite":
            return False
        row = db.execute(
            text(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='dossier_archive_fts' LIMIT 1"
            )
        ).first()
        return row is not None
    except Exception as e:
        logger.debug("dossier_archive_fts check failed: %s", e)
        return False


def _snippet(body: str, query: str, width: int = 160) -> str:
    text_body = body or ""
    lower = text_body.lower()
    tokens = [t for t in re.findall(r"[\w][\w._-]*", query, flags=re.UNICODE) if t]
    idx = -1
    for tok in tokens:
        idx = lower.find(tok.lower())
        if idx >= 0:
            break
    if idx < 0:
        return text_body[:width] + ("…" if len(text_body) > width else "")
    start = max(0, idx - width // 3)
    end = min(len(text_body), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text_body) else ""
    return prefix + text_body[start:end] + suffix


def search_archive(
    query: str,
    *,
    owner: str,
    db: Session,
    person_id: Optional[str] = None,
    situation_id: Optional[str] = None,
    limit: int = 10,
) -> list[ArchiveSearchHit]:
    q = (query or "").strip()
    if not q or not owner:
        return []
    limit = max(1, min(int(limit or 10), 50))

    if _has_archive_fts(db):
        fts_q = _sanitize_fts_query(q)
        if fts_q:
            try:
                sql = """
                    SELECT a.id, a.source_tool, a.external_id, a.locator, a.body,
                           a.person_id, a.situation_id, a.captured_at,
                           snippet(dossier_archive_fts, 0, '', '', '…', 24) AS snip
                    FROM dossier_archive_fts
                    JOIN dossier_archive_items a ON a.id = dossier_archive_fts.item_id
                    WHERE dossier_archive_fts MATCH :q
                      AND a.owner = :owner
                """
                params: dict[str, Any] = {"q": fts_q, "owner": owner}
                if person_id:
                    sql += " AND a.person_id = :person_id"
                    params["person_id"] = person_id
                if situation_id:
                    sql += " AND a.situation_id = :situation_id"
                    params["situation_id"] = situation_id
                sql += " ORDER BY bm25(dossier_archive_fts) LIMIT :limit"
                params["limit"] = limit
                rows = db.execute(text(sql), params).fetchall()
                hits: list[ArchiveSearchHit] = []
                for row in rows:
                    captured = row[7]
                    hits.append(
                        ArchiveSearchHit(
                            item_id=row[0],
                            source_tool=row[1],
                            external_id=row[2],
                            locator=row[3],
                            snippet=(row[8] or _snippet(row[4] or "", q)).strip(),
                            person_id=row[5],
                            situation_id=row[6],
                            captured_at=captured.isoformat() if hasattr(captured, "isoformat") else (
                                str(captured) if captured else None
                            ),
                        )
                    )
                return hits
            except Exception as e:
                logger.debug("dossier archive FTS search failed, falling back: %s", e)

    # LIKE fallback
    filt = (
        db.query(DossierArchiveItem)
        .filter(
            DossierArchiveItem.owner == owner,
            DossierArchiveItem.body.ilike(f"%{q}%"),
        )
    )
    if person_id:
        filt = filt.filter(DossierArchiveItem.person_id == person_id)
    if situation_id:
        filt = filt.filter(DossierArchiveItem.situation_id == situation_id)
    rows = filt.order_by(DossierArchiveItem.captured_at.desc()).limit(limit).all()
    return [
        ArchiveSearchHit(
            item_id=item.id,
            source_tool=item.source_tool,
            external_id=item.external_id,
            locator=item.locator,
            snippet=_snippet(item.body or "", q),
            person_id=item.person_id,
            situation_id=item.situation_id,
            captured_at=item.captured_at.isoformat() if item.captured_at else None,
        )
        for item in rows
    ]
