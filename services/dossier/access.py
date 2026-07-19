"""Dossier schema helpers: validation and owner-scoped access."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Iterable, List, Optional, Sequence

from sqlalchemy.orm import Session

from core.database import (
    DossierArchiveItem,
    DossierKeyFact,
    DossierPerson,
    DossierPlan,
    DossierSituation,
    DossierTimelineEvent,
    utcnow_naive,
)

ALLOWED_SOURCE_TOOLS = frozenset({"paste", "import"})


def new_id() -> str:
    return str(uuid.uuid4())


def dumps_labels(labels: Iterable[str]) -> str:
    cleaned = sorted({str(x).strip().lower() for x in labels if str(x).strip()})
    return json.dumps(cleaned)


def loads_labels(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]


def dumps_ids(ids: Optional[Sequence[str]]) -> str:
    if not ids:
        return "[]"
    return json.dumps([str(x) for x in ids if x])


def loads_ids(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x) for x in data]


def normalize_source_tool(source_tool: Optional[str]) -> str:
    """Require a non-empty source_tool (tool name, paste, or import)."""
    value = (source_tool or "").strip()
    if not value:
        raise ValueError("source_tool is required")
    return value


def get_person(db: Session, person_id: str, owner: str) -> Optional[DossierPerson]:
    return (
        db.query(DossierPerson)
        .filter(DossierPerson.id == person_id, DossierPerson.owner == owner)
        .first()
    )


def get_situation(db: Session, situation_id: str, owner: str) -> Optional[DossierSituation]:
    return (
        db.query(DossierSituation)
        .filter(DossierSituation.id == situation_id, DossierSituation.owner == owner)
        .first()
    )


def get_archive_item(db: Session, item_id: str, owner: str) -> Optional[DossierArchiveItem]:
    return (
        db.query(DossierArchiveItem)
        .filter(DossierArchiveItem.id == item_id, DossierArchiveItem.owner == owner)
        .first()
    )


def get_plan(db: Session, plan_id: str, owner: str) -> Optional[DossierPlan]:
    return (
        db.query(DossierPlan)
        .filter(DossierPlan.id == plan_id, DossierPlan.owner == owner)
        .first()
    )


def get_fact(db: Session, fact_id: str, owner: str) -> Optional[DossierKeyFact]:
    return (
        db.query(DossierKeyFact)
        .filter(DossierKeyFact.id == fact_id, DossierKeyFact.owner == owner)
        .first()
    )


def create_person(
    db: Session,
    *,
    owner: str,
    display_name: str,
    labels: Optional[Sequence[str]] = None,
    carddav_uid: Optional[str] = None,
    sysforge_client_id: Optional[str] = None,
    notes: Optional[str] = None,
) -> DossierPerson:
    person = DossierPerson(
        id=new_id(),
        owner=owner,
        display_name=(display_name or "").strip() or "Unnamed",
        labels=dumps_labels(labels or []),
        carddav_uid=carddav_uid or None,
        sysforge_client_id=sysforge_client_id or None,
        notes=notes,
    )
    db.add(person)
    db.flush()
    return person


def create_situation(
    db: Session,
    *,
    owner: str,
    person_id: str,
    title: str,
    status: str = "active",
    summary: Optional[str] = None,
) -> DossierSituation:
    if not get_person(db, person_id, owner):
        raise LookupError("person not found")
    situation = DossierSituation(
        id=new_id(),
        owner=owner,
        person_id=person_id,
        title=(title or "").strip() or "Untitled situation",
        status=status or "active",
        summary=summary,
    )
    db.add(situation)
    db.flush()
    return situation


def create_archive_item(
    db: Session,
    *,
    owner: str,
    source_tool: str,
    body: str,
    external_id: Optional[str] = None,
    locator: Optional[str] = None,
    captured_at: Optional[datetime] = None,
    person_id: Optional[str] = None,
    situation_id: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> DossierArchiveItem:
    tool = normalize_source_tool(source_tool)
    text = body if body is not None else ""
    if not str(text).strip():
        raise ValueError("body is required")
    if person_id and not get_person(db, person_id, owner):
        raise LookupError("person not found")
    if situation_id and not get_situation(db, situation_id, owner):
        raise LookupError("situation not found")
    item = DossierArchiveItem(
        id=new_id(),
        owner=owner,
        source_tool=tool,
        external_id=external_id,
        locator=locator,
        body=str(text),
        captured_at=captured_at or utcnow_naive(),
        person_id=person_id,
        situation_id=situation_id,
        content_hash=content_hash,
    )
    db.add(item)
    db.flush()
    return item


def create_plan(
    db: Session,
    *,
    owner: str,
    person_id: str,
    title: str,
    summary: str,
    how_we_got_here: Optional[str] = None,
    situation_id: Optional[str] = None,
    source_archive_ids: Optional[Sequence[str]] = None,
    origin: Optional[str] = None,
) -> DossierPlan:
    if not get_person(db, person_id, owner):
        raise LookupError("person not found")
    if situation_id and not get_situation(db, situation_id, owner):
        raise LookupError("situation not found")
    plan = DossierPlan(
        id=new_id(),
        owner=owner,
        person_id=person_id,
        situation_id=situation_id,
        title=(title or "").strip() or "Plan",
        summary=summary or "",
        how_we_got_here=how_we_got_here,
        source_archive_ids=dumps_ids(source_archive_ids),
        origin=origin,
    )
    db.add(plan)
    db.flush()
    return plan


def create_fact(
    db: Session,
    *,
    owner: str,
    person_id: str,
    label: str,
    value: str,
    situation_id: Optional[str] = None,
    source_archive_ids: Optional[Sequence[str]] = None,
) -> DossierKeyFact:
    if not get_person(db, person_id, owner):
        raise LookupError("person not found")
    if situation_id and not get_situation(db, situation_id, owner):
        raise LookupError("situation not found")
    fact = DossierKeyFact(
        id=new_id(),
        owner=owner,
        person_id=person_id,
        situation_id=situation_id,
        label=(label or "").strip() or "fact",
        value=value or "",
        source_archive_ids=dumps_ids(source_archive_ids),
    )
    db.add(fact)
    db.flush()
    return fact


def add_timeline_event(
    db: Session,
    *,
    owner: str,
    person_id: str,
    summary: str,
    event_type: str = "note",
    situation_id: Optional[str] = None,
    ref_kind: Optional[str] = None,
    ref_id: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
) -> DossierTimelineEvent:
    if not get_person(db, person_id, owner):
        raise LookupError("person not found")
    event = DossierTimelineEvent(
        id=new_id(),
        owner=owner,
        person_id=person_id,
        situation_id=situation_id,
        event_type=event_type or "note",
        summary=summary or "",
        ref_kind=ref_kind,
        ref_id=ref_id,
        occurred_at=occurred_at or utcnow_naive(),
    )
    db.add(event)
    db.flush()
    return event


def person_to_dict(person: DossierPerson) -> dict[str, Any]:
    return {
        "id": person.id,
        "owner": person.owner,
        "display_name": person.display_name,
        "labels": loads_labels(person.labels),
        "carddav_uid": person.carddav_uid,
        "sysforge_client_id": person.sysforge_client_id,
        "notes": person.notes,
        "created_at": person.created_at.isoformat() if person.created_at else None,
        "updated_at": person.updated_at.isoformat() if person.updated_at else None,
    }


def archive_to_dict(item: DossierArchiveItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "owner": item.owner,
        "source_tool": item.source_tool,
        "external_id": item.external_id,
        "locator": item.locator,
        "body": item.body,
        "captured_at": item.captured_at.isoformat() if item.captured_at else None,
        "person_id": item.person_id,
        "situation_id": item.situation_id,
        "content_hash": item.content_hash,
    }
