"""U1: dossier schema and owner-scoped helpers."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base
from services.dossier import access


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_person_friend_and_client_labels():
    db = _db()
    person = access.create_person(
        db, owner="alice", display_name="Sam", labels=["friend", "client"]
    )
    db.commit()
    loaded = access.get_person(db, person.id, "alice")
    assert loaded is not None
    assert set(access.loads_labels(loaded.labels)) == {"friend", "client"}
    assert loaded.carddav_uid is None
    assert loaded.sysforge_client_id is None


def test_situation_plan_fact_link_to_person():
    db = _db()
    person = access.create_person(db, owner="alice", display_name="Pat")
    situation = access.create_situation(
        db, owner="alice", person_id=person.id, title="Fan repair"
    )
    plan = access.create_plan(
        db,
        owner="alice",
        person_id=person.id,
        situation_id=situation.id,
        title="Next steps",
        summary="Replace fan if error returns",
        how_we_got_here="Discussed on visit",
    )
    fact = access.create_fact(
        db,
        owner="alice",
        person_id=person.id,
        situation_id=situation.id,
        label="fan_model",
        value="Cooler Master X",
    )
    db.commit()
    assert plan.situation_id == situation.id
    assert fact.person_id == person.id
    assert access.get_situation(db, situation.id, "alice").title == "Fan repair"


def test_archive_requires_source_tool_and_body():
    db = _db()
    with pytest.raises(ValueError, match="source_tool"):
        access.create_archive_item(db, owner="alice", source_tool="", body="hello")
    with pytest.raises(ValueError, match="body"):
        access.create_archive_item(db, owner="alice", source_tool="paste", body="  ")
    item = access.create_archive_item(
        db,
        owner="alice",
        source_tool="plaud",
        body="Transcript line about fan",
        locator="chunk:12",
        external_id="rec-1",
    )
    db.commit()
    assert item.source_tool == "plaud"
    assert item.locator == "chunk:12"


def test_owner_isolation_on_get():
    db = _db()
    person = access.create_person(db, owner="alice", display_name="Only Alice")
    db.commit()
    assert access.get_person(db, person.id, "alice") is not None
    assert access.get_person(db, person.id, "bob") is None


def test_optional_carddav_and_sysforge_ids():
    db = _db()
    person = access.create_person(
        db,
        owner="alice",
        display_name="Jordan",
        carddav_uid="uid-1",
        sysforge_client_id="42",
    )
    db.commit()
    loaded = access.get_person(db, person.id, "alice")
    assert loaded.carddav_uid == "uid-1"
    assert loaded.sysforge_client_id == "42"
