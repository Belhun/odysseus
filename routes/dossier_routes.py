"""People dossier + archive API (browse, cite open, link correct)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.database import (
    SessionLocal,
    DossierArchiveItem,
    DossierKeyFact,
    DossierPlan,
    DossierSituation,
    DossierTimelineEvent,
)
from src.auth_helpers import require_user
from services.dossier import access
from src.tools.dossier import (
    _fact_dict,
    _plan_dict,
    _situation_dict,
    _timeline_dict,
)


class PersonCreate(BaseModel):
    display_name: str = ""
    labels: List[str] = Field(default_factory=list)
    carddav_uid: Optional[str] = None
    sysforge_client_id: Optional[str] = None
    notes: Optional[str] = None


class PersonUpdate(BaseModel):
    display_name: Optional[str] = None
    labels: Optional[List[str]] = None
    notes: Optional[str] = None


class SituationCreate(BaseModel):
    title: str = ""
    status: str = "active"
    summary: Optional[str] = None


class PlanCreate(BaseModel):
    title: str = "Plan"
    summary: str = ""
    how_we_got_here: Optional[str] = None
    situation_id: Optional[str] = None


class FactCreate(BaseModel):
    label: str = ""
    value: str = ""
    situation_id: Optional[str] = None


class TimelineCreate(BaseModel):
    summary: str = ""
    situation_id: Optional[str] = None


class ArchivePaste(BaseModel):
    body: str = ""
    source_tool: str = "paste"
    locator: Optional[str] = None
    situation_id: Optional[str] = None


class LinkUpdate(BaseModel):
    person_id: Optional[str] = None
    situation_id: Optional[str] = None


def setup_dossier_routes() -> APIRouter:
    router = APIRouter(prefix="/api/dossier", tags=["dossier"])

    def _owner(request: Request) -> str:
        user = require_user(request)
        return user

    @router.get("/people")
    def list_people(request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            from core.database import DossierPerson

            rows = (
                db.query(DossierPerson)
                .filter(DossierPerson.owner == owner)
                .order_by(DossierPerson.display_name.asc())
                .all()
            )
            return {"people": [access.person_to_dict(p) for p in rows]}
        finally:
            db.close()

    @router.post("/people")
    def create_person(body: PersonCreate, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            person = access.create_person(
                db,
                owner=owner,
                display_name=body.display_name,
                labels=body.labels,
                carddav_uid=body.carddav_uid,
                sysforge_client_id=body.sysforge_client_id,
                notes=body.notes,
            )
            db.commit()
            return {"person": access.person_to_dict(person)}
        finally:
            db.close()

    @router.patch("/people/{person_id}")
    def update_person(person_id: str, body: PersonUpdate, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            person = access.get_person(db, person_id, owner)
            if not person:
                raise HTTPException(status_code=404, detail="person not found")
            if body.display_name is not None:
                person.display_name = body.display_name.strip() or person.display_name
            if body.labels is not None:
                person.labels = access.dumps_labels(body.labels)
            if body.notes is not None:
                person.notes = body.notes
            db.commit()
            return {"person": access.person_to_dict(person)}
        finally:
            db.close()

    @router.get("/people/{person_id}")
    def get_dossier(person_id: str, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            person = access.get_person(db, person_id, owner)
            if not person:
                raise HTTPException(status_code=404, detail="person not found")
            pid = person.id
            return {
                "person": access.person_to_dict(person),
                "situations": [
                    _situation_dict(s)
                    for s in db.query(DossierSituation)
                    .filter(DossierSituation.owner == owner, DossierSituation.person_id == pid)
                    .all()
                ],
                "plans": [
                    _plan_dict(p)
                    for p in db.query(DossierPlan)
                    .filter(DossierPlan.owner == owner, DossierPlan.person_id == pid)
                    .all()
                ],
                "facts": [
                    _fact_dict(f)
                    for f in db.query(DossierKeyFact)
                    .filter(DossierKeyFact.owner == owner, DossierKeyFact.person_id == pid)
                    .all()
                ],
                "timeline": [
                    _timeline_dict(e)
                    for e in db.query(DossierTimelineEvent)
                    .filter(
                        DossierTimelineEvent.owner == owner,
                        DossierTimelineEvent.person_id == pid,
                    )
                    .order_by(DossierTimelineEvent.occurred_at.desc())
                    .limit(100)
                    .all()
                ],
                "archive": [
                    access.archive_to_dict(a)
                    for a in db.query(DossierArchiveItem)
                    .filter(
                        DossierArchiveItem.owner == owner,
                        DossierArchiveItem.person_id == pid,
                    )
                    .order_by(DossierArchiveItem.captured_at.desc())
                    .limit(100)
                    .all()
                ],
            }
        finally:
            db.close()

    @router.post("/people/{person_id}/situations")
    def create_situation(person_id: str, body: SituationCreate, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            try:
                situation = access.create_situation(
                    db,
                    owner=owner,
                    person_id=person_id,
                    title=body.title,
                    status=body.status,
                    summary=body.summary,
                )
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=person_id,
                    situation_id=situation.id,
                    event_type="situation_created",
                    summary=f"Situation: {situation.title}",
                    ref_kind="situation",
                    ref_id=situation.id,
                )
                db.commit()
                return {"situation": _situation_dict(situation)}
            except LookupError:
                db.rollback()
                raise HTTPException(status_code=404, detail="person not found")
        finally:
            db.close()

    @router.post("/people/{person_id}/plans")
    def create_plan(person_id: str, body: PlanCreate, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            try:
                plan = access.create_plan(
                    db,
                    owner=owner,
                    person_id=person_id,
                    situation_id=body.situation_id,
                    title=body.title,
                    summary=body.summary,
                    how_we_got_here=body.how_we_got_here,
                    origin="manual",
                )
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=person_id,
                    situation_id=plan.situation_id,
                    event_type="plan_saved",
                    summary=f"Plan saved: {plan.title}",
                    ref_kind="plan",
                    ref_id=plan.id,
                )
                db.commit()
                return {"plan": _plan_dict(plan)}
            except LookupError as e:
                db.rollback()
                raise HTTPException(status_code=404, detail=str(e))
        finally:
            db.close()

    @router.post("/people/{person_id}/facts")
    def create_fact(person_id: str, body: FactCreate, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            try:
                fact = access.create_fact(
                    db,
                    owner=owner,
                    person_id=person_id,
                    situation_id=body.situation_id,
                    label=body.label,
                    value=body.value,
                )
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=person_id,
                    situation_id=fact.situation_id,
                    event_type="fact_saved",
                    summary=f"Fact: {fact.label}",
                    ref_kind="fact",
                    ref_id=fact.id,
                )
                db.commit()
                return {"fact": _fact_dict(fact)}
            except LookupError as e:
                db.rollback()
                raise HTTPException(status_code=404, detail=str(e))
        finally:
            db.close()

    @router.post("/people/{person_id}/timeline")
    def create_timeline_note(person_id: str, body: TimelineCreate, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            try:
                event = access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=person_id,
                    situation_id=body.situation_id,
                    summary=body.summary,
                    event_type="note",
                )
                db.commit()
                return {"event": _timeline_dict(event)}
            except LookupError:
                db.rollback()
                raise HTTPException(status_code=404, detail="person not found")
        finally:
            db.close()

    @router.post("/people/{person_id}/archive")
    def paste_archive(person_id: str, body: ArchivePaste, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            try:
                item = access.create_archive_item(
                    db,
                    owner=owner,
                    source_tool=body.source_tool,
                    body=body.body,
                    person_id=person_id,
                    situation_id=body.situation_id,
                    locator=body.locator,
                )
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=person_id,
                    situation_id=body.situation_id,
                    event_type="archive_ingested",
                    summary="Archive item pasted",
                    ref_kind="archive",
                    ref_id=item.id,
                )
                db.commit()
                return {"item": access.archive_to_dict(item)}
            except LookupError as e:
                db.rollback()
                raise HTTPException(status_code=404, detail=str(e))
            except ValueError as e:
                db.rollback()
                raise HTTPException(status_code=400, detail=str(e))
        finally:
            db.close()

    @router.get("/archive/{item_id}")
    def get_archive(item_id: str, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            item = access.get_archive_item(db, item_id, owner)
            if not item:
                raise HTTPException(status_code=404, detail="archive item not found")
            return {"item": access.archive_to_dict(item)}
        finally:
            db.close()

    @router.patch("/archive/{item_id}/link")
    def update_archive_link(item_id: str, body: LinkUpdate, request: Request):
        """Assign or correct person/situation link on an archive item."""
        owner = _owner(request)
        db = SessionLocal()
        try:
            item = access.get_archive_item(db, item_id, owner)
            if not item:
                raise HTTPException(status_code=404, detail="archive item not found")
            if body.person_id is not None:
                if body.person_id and not access.get_person(db, body.person_id, owner):
                    raise HTTPException(status_code=404, detail="person not found")
                item.person_id = body.person_id or None
            if body.situation_id is not None:
                if body.situation_id and not access.get_situation(db, body.situation_id, owner):
                    raise HTTPException(status_code=404, detail="situation not found")
                item.situation_id = body.situation_id or None
            if item.person_id:
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=item.person_id,
                    situation_id=item.situation_id,
                    event_type="link_updated",
                    summary="Archive link updated",
                    ref_kind="archive",
                    ref_id=item.id,
                )
            db.commit()
            return {"item": access.archive_to_dict(item)}
        finally:
            db.close()

    @router.get("/plans/{plan_id}")
    def get_plan(plan_id: str, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            plan = access.get_plan(db, plan_id, owner)
            if not plan:
                raise HTTPException(status_code=404, detail="plan not found")
            return {"plan": _plan_dict(plan)}
        finally:
            db.close()

    @router.get("/situations/{situation_id}")
    def get_situation(situation_id: str, request: Request):
        owner = _owner(request)
        db = SessionLocal()
        try:
            situation = access.get_situation(db, situation_id, owner)
            if not situation:
                raise HTTPException(status_code=404, detail="situation not found")
            return {"situation": _situation_dict(situation)}
        finally:
            db.close()

    return router
