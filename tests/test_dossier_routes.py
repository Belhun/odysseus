"""HTTP dossier routes — owner scoping and link writes."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.database import Base
from routes.dossier_routes import setup_dossier_routes
from services.dossier import access


def _client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("core.database.SessionLocal", lambda: Session())
    monkeypatch.setattr("routes.dossier_routes.SessionLocal", lambda: Session())
    monkeypatch.setattr("routes.dossier_routes.require_user", lambda request: "alice")

    app = FastAPI()
    app.include_router(setup_dossier_routes())
    return TestClient(app), Session


def test_dossier_get_and_link_write(monkeypatch):
    client, Session = _client(monkeypatch)
    db = Session()
    person = access.create_person(
        db, owner="alice", display_name="Sam", labels=["friend", "client"]
    )
    other = access.create_person(db, owner="alice", display_name="Wrong")
    item = access.create_archive_item(
        db,
        owner="alice",
        source_tool="plaud",
        body="fan transcript",
        person_id=other.id,
        locator="chunk:1",
    )
    db.commit()
    pid, iid = person.id, item.id
    db.close()

    r = client.get(f"/api/dossier/people/{pid}")
    assert r.status_code == 200
    body = r.json()
    assert set(body["person"]["labels"]) == {"friend", "client"}
    assert body["situations"] == []
    assert body["plans"] == []

    ar = client.get(f"/api/dossier/archive/{iid}")
    assert ar.status_code == 200
    assert ar.json()["item"]["source_tool"] == "plaud"

    link = client.patch(
        f"/api/dossier/archive/{iid}/link",
        json={"person_id": pid},
    )
    assert link.status_code == 200
    assert link.json()["item"]["person_id"] == pid

    # other owner isolation
    monkeypatch.setattr("routes.dossier_routes.require_user", lambda request: "bob")
    denied = client.get(f"/api/dossier/people/{pid}")
    assert denied.status_code == 404
