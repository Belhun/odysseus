"""manage_dossier tool — person/situation/plan/fact/timeline/link CRUD."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from src.tools._common import _parse_tool_args
from services.dossier import access

logger = logging.getLogger(__name__)


def _situation_dict(s) -> dict:
    return {
        "id": s.id,
        "person_id": s.person_id,
        "title": s.title,
        "status": s.status,
        "summary": s.summary,
    }


def _plan_dict(p) -> dict:
    return {
        "id": p.id,
        "person_id": p.person_id,
        "situation_id": p.situation_id,
        "title": p.title,
        "summary": p.summary,
        "how_we_got_here": p.how_we_got_here,
        "source_archive_ids": access.loads_ids(p.source_archive_ids),
        "origin": p.origin,
    }


def _fact_dict(f) -> dict:
    return {
        "id": f.id,
        "person_id": f.person_id,
        "situation_id": f.situation_id,
        "label": f.label,
        "value": f.value,
        "source_archive_ids": access.loads_ids(f.source_archive_ids),
    }


def _timeline_dict(e) -> dict:
    return {
        "id": e.id,
        "person_id": e.person_id,
        "situation_id": e.situation_id,
        "event_type": e.event_type,
        "summary": e.summary,
        "ref_kind": e.ref_kind,
        "ref_id": e.ref_id,
        "occurred_at": e.occurred_at.isoformat() if e.occurred_at else None,
    }


def _propose_person_candidates(db, owner: str, hint: str) -> List[dict]:
    from core.database import DossierPerson

    hint_l = (hint or "").strip().lower()
    rows = db.query(DossierPerson).filter(DossierPerson.owner == owner).all()
    scored = []
    for p in rows:
        name = (p.display_name or "").lower()
        score = 0
        if hint_l and hint_l in name:
            score = 10 if name == hint_l else 5
        scored.append((score, p))
    scored.sort(key=lambda x: (-x[0], (x[1].display_name or "").lower()))
    out = []
    for score, p in scored[:8]:
        if score == 0 and hint_l:
            continue
        out.append({**access.person_to_dict(p), "confidence": score})
    if not out and not hint_l:
        out = [access.person_to_dict(p) for _, p in scored[:8]]
    return out


async def do_manage_dossier(content: str, owner: Optional[str] = None) -> Dict:
    from core.database import (
        SessionLocal,
        DossierArchiveItem,
        DossierKeyFact,
        DossierPerson,
        DossierPlan,
        DossierSituation,
        DossierTimelineEvent,
    )

    if not owner:
        return {"error": "owner required", "exit_code": 1}
    try:
        args = _parse_tool_args(content)
    except ValueError:
        return {"error": "Invalid JSON arguments", "exit_code": 1}

    action = (args.get("action") or "").replace("-", "_").strip().lower()
    db = SessionLocal()
    try:
        # --- person ---
        if action in ("person_create", "create_person"):
            person = access.create_person(
                db,
                owner=owner,
                display_name=args.get("display_name") or args.get("name") or "",
                labels=args.get("labels") or [],
                carddav_uid=args.get("carddav_uid"),
                sysforge_client_id=args.get("sysforge_client_id"),
                notes=args.get("notes"),
            )
            db.commit()
            return {"ok": True, "person": access.person_to_dict(person)}

        if action in ("person_get", "get_person"):
            person = access.get_person(db, args.get("person_id") or args.get("id") or "", owner)
            if not person:
                return {"error": "person not found", "exit_code": 1}
            return {"ok": True, "person": access.person_to_dict(person)}

        if action in ("person_list", "list_people"):
            rows = (
                db.query(DossierPerson)
                .filter(DossierPerson.owner == owner)
                .order_by(DossierPerson.display_name.asc())
                .all()
            )
            return {"ok": True, "people": [access.person_to_dict(p) for p in rows]}

        if action in ("person_update", "update_person"):
            person = access.get_person(db, args.get("person_id") or args.get("id") or "", owner)
            if not person:
                return {"error": "person not found", "exit_code": 1}
            if args.get("display_name") is not None or args.get("name") is not None:
                person.display_name = (args.get("display_name") or args.get("name") or "").strip()
            if args.get("labels") is not None:
                person.labels = access.dumps_labels(args.get("labels") or [])
            if "carddav_uid" in args:
                person.carddav_uid = args.get("carddav_uid") or None
            if "sysforge_client_id" in args:
                person.sysforge_client_id = args.get("sysforge_client_id") or None
            if "notes" in args:
                person.notes = args.get("notes")
            db.commit()
            return {"ok": True, "person": access.person_to_dict(person)}

        # --- situation ---
        if action in ("situation_create", "create_situation"):
            try:
                situation = access.create_situation(
                    db,
                    owner=owner,
                    person_id=args.get("person_id") or "",
                    title=args.get("title") or "",
                    status=args.get("status") or "active",
                    summary=args.get("summary"),
                )
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=situation.person_id,
                    situation_id=situation.id,
                    event_type="situation_created",
                    summary=f"Situation: {situation.title}",
                    ref_kind="situation",
                    ref_id=situation.id,
                )
                db.commit()
                return {"ok": True, "situation": _situation_dict(situation)}
            except LookupError as e:
                db.rollback()
                return {"error": str(e), "exit_code": 1}

        if action in ("situation_get", "get_situation"):
            situation = access.get_situation(
                db, args.get("situation_id") or args.get("id") or "", owner
            )
            if not situation:
                return {"error": "situation not found", "exit_code": 1}
            return {"ok": True, "situation": _situation_dict(situation)}

        if action in ("situation_list", "list_situations"):
            q = db.query(DossierSituation).filter(DossierSituation.owner == owner)
            if args.get("person_id"):
                q = q.filter(DossierSituation.person_id == args["person_id"])
            rows = q.order_by(DossierSituation.updated_at.desc()).all()
            return {"ok": True, "situations": [_situation_dict(s) for s in rows]}

        # --- plan ---
        if action in ("plan_save", "save_plan", "plan_create"):
            try:
                plan = access.create_plan(
                    db,
                    owner=owner,
                    person_id=args.get("person_id") or "",
                    situation_id=args.get("situation_id"),
                    title=args.get("title") or "Plan",
                    summary=args.get("summary") or args.get("plan") or "",
                    how_we_got_here=args.get("how_we_got_here") or args.get("context"),
                    source_archive_ids=args.get("source_archive_ids") or [],
                    origin=args.get("origin") or "manual",
                )
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=plan.person_id,
                    situation_id=plan.situation_id,
                    event_type="plan_saved",
                    summary=f"Plan saved: {plan.title}",
                    ref_kind="plan",
                    ref_id=plan.id,
                )
                db.commit()
                return {"ok": True, "plan": _plan_dict(plan)}
            except LookupError as e:
                db.rollback()
                return {"error": str(e), "exit_code": 1}

        if action in ("plan_get", "get_plan"):
            plan = access.get_plan(db, args.get("plan_id") or args.get("id") or "", owner)
            if not plan:
                return {"error": "plan not found", "exit_code": 1}
            return {"ok": True, "plan": _plan_dict(plan)}

        if action in ("plan_list", "list_plans"):
            q = db.query(DossierPlan).filter(DossierPlan.owner == owner)
            if args.get("person_id"):
                q = q.filter(DossierPlan.person_id == args["person_id"])
            if args.get("situation_id"):
                q = q.filter(DossierPlan.situation_id == args["situation_id"])
            rows = q.order_by(DossierPlan.updated_at.desc()).all()
            return {"ok": True, "plans": [_plan_dict(p) for p in rows]}

        # --- fact ---
        if action in ("fact_save", "save_fact", "fact_create"):
            try:
                fact = access.create_fact(
                    db,
                    owner=owner,
                    person_id=args.get("person_id") or "",
                    situation_id=args.get("situation_id"),
                    label=args.get("label") or "",
                    value=args.get("value") or "",
                    source_archive_ids=args.get("source_archive_ids") or [],
                )
                access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=fact.person_id,
                    situation_id=fact.situation_id,
                    event_type="fact_saved",
                    summary=f"Fact: {fact.label}",
                    ref_kind="fact",
                    ref_id=fact.id,
                )
                db.commit()
                return {"ok": True, "fact": _fact_dict(fact)}
            except LookupError as e:
                db.rollback()
                return {"error": str(e), "exit_code": 1}

        if action in ("fact_list", "list_facts"):
            q = db.query(DossierKeyFact).filter(DossierKeyFact.owner == owner)
            if args.get("person_id"):
                q = q.filter(DossierKeyFact.person_id == args["person_id"])
            if args.get("situation_id"):
                q = q.filter(DossierKeyFact.situation_id == args["situation_id"])
            rows = q.order_by(DossierKeyFact.updated_at.desc()).all()
            return {"ok": True, "facts": [_fact_dict(f) for f in rows]}

        # --- timeline ---
        if action in ("timeline_list", "list_timeline"):
            person_id = args.get("person_id") or ""
            if not person_id:
                return {"error": "person_id required", "exit_code": 1}
            q = db.query(DossierTimelineEvent).filter(
                DossierTimelineEvent.owner == owner,
                DossierTimelineEvent.person_id == person_id,
            )
            if args.get("situation_id"):
                q = q.filter(DossierTimelineEvent.situation_id == args["situation_id"])
            rows = q.order_by(DossierTimelineEvent.occurred_at.desc()).limit(100).all()
            return {"ok": True, "events": [_timeline_dict(e) for e in rows]}

        if action in ("timeline_add", "add_timeline"):
            try:
                event = access.add_timeline_event(
                    db,
                    owner=owner,
                    person_id=args.get("person_id") or "",
                    situation_id=args.get("situation_id"),
                    summary=args.get("summary") or "",
                    event_type=args.get("event_type") or "note",
                )
                db.commit()
                return {"ok": True, "event": _timeline_dict(event)}
            except LookupError as e:
                db.rollback()
                return {"error": str(e), "exit_code": 1}

        # --- links ---
        if action in ("link_propose", "propose_link"):
            hint = args.get("hint") or args.get("name") or args.get("query") or ""
            return {
                "ok": True,
                "candidates": _propose_person_candidates(db, owner, hint),
                "note": "Confirm with link_assign or fix with link_correct.",
            }

        if action in ("link_assign", "assign_link", "link_correct", "correct_link"):
            item_id = args.get("archive_id") or args.get("item_id") or args.get("id") or ""
            person_id = args.get("person_id")
            situation_id = args.get("situation_id")
            item = access.get_archive_item(db, item_id, owner)
            if not item:
                return {"error": "archive item not found", "exit_code": 1}
            if person_id:
                if not access.get_person(db, person_id, owner):
                    return {"error": "person not found", "exit_code": 1}
                item.person_id = person_id
            if situation_id is not None:
                if situation_id and not access.get_situation(db, situation_id, owner):
                    return {"error": "situation not found", "exit_code": 1}
                item.situation_id = situation_id or None
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
            return {"ok": True, "item": access.archive_to_dict(item)}

        if action in ("dossier_get", "get_dossier"):
            person = access.get_person(db, args.get("person_id") or args.get("id") or "", owner)
            if not person:
                return {"error": "person not found", "exit_code": 1}
            pid = person.id
            return {
                "ok": True,
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
                    .limit(50)
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
                    .limit(50)
                    .all()
                ],
            }

        return {
            "error": (
                f"Unknown action '{action}'. Use person_*, situation_*, plan_*, "
                "fact_*, timeline_*, link_*, or dossier_get."
            ),
            "exit_code": 1,
        }
    except Exception as e:
        logger.exception("manage_dossier failed")
        db.rollback()
        return {"error": str(e), "exit_code": 1}
    finally:
        db.close()
