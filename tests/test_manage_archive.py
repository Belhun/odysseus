"""U2/U3/U4 tool tests for archive, dossier, search."""
import json
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.database import Base, SessionLocal
from services.dossier import access
from services.dossier.archive_search import search_archive


def _mem_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.execute(
        text(
            """
            CREATE VIRTUAL TABLE dossier_archive_fts USING fts5(
                body,
                item_id UNINDEXED,
                owner UNINDEXED
            )
            """
        )
    )
    return db, engine


def _index_fts(db, item):
    db.execute(
        text(
            "INSERT INTO dossier_archive_fts(body, item_id, owner) VALUES (:b, :i, :o)"
        ),
        {"b": item.body, "i": item.id, "o": item.owner},
    )


@pytest.mark.asyncio
async def test_manage_archive_ingest_get_search(monkeypatch):
    db, engine = _mem_db()
    Session = sessionmaker(bind=engine)

    def _session():
        return Session()

    monkeypatch.setattr("core.database.SessionLocal", _session)
    from src.tools.archive import do_manage_archive

    ingest = await do_manage_archive(
        json.dumps(
            {
                "action": "ingest",
                "source_tool": "plaud",
                "body": "If the fan error returns, replace the fan assembly.",
                "locator": "chunk:4",
                "external_id": "rec-9",
            }
        ),
        owner="alice",
    )
    assert ingest.get("ok")
    item_id = ingest["item"]["id"]

    got = await do_manage_archive(json.dumps({"action": "get", "id": item_id}), owner="alice")
    assert got["item"]["source_tool"] == "plaud"

    # Index for FTS (triggers only on real DB migrations)
    s = Session()
    item = access.get_archive_item(s, item_id, "alice")
    _index_fts(s, item)
    s.commit()
    s.close()

    search = await do_manage_archive(
        json.dumps({"action": "search", "query": "fan error"}), owner="alice"
    )
    assert search.get("ok")
    assert any(h["id"] == item_id for h in search["hits"])


@pytest.mark.asyncio
async def test_manage_dossier_plan_link_correct(monkeypatch):
    db, engine = _mem_db()
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("core.database.SessionLocal", lambda: Session())
    from src.tools.dossier import do_manage_dossier
    from src.tools.archive import do_manage_archive

    person = await do_manage_dossier(
        json.dumps(
            {
                "action": "person_create",
                "display_name": "Client Sam",
                "labels": ["friend", "client"],
            }
        ),
        owner="alice",
    )
    pid = person["person"]["id"]
    other = await do_manage_dossier(
        json.dumps({"action": "person_create", "display_name": "Wrong Person"}),
        owner="alice",
    )
    wrong_id = other["person"]["id"]
    sit = await do_manage_dossier(
        json.dumps({"action": "situation_create", "person_id": pid, "title": "Fan repair"}),
        owner="alice",
    )
    sid = sit["situation"]["id"]

    paste = await do_manage_archive(
        json.dumps(
            {
                "action": "ingest",
                "source_tool": "paste",
                "body": "Other AI plan: replace fan if error returns. Discussed during visit.",
                "person_id": wrong_id,
            }
        ),
        owner="alice",
    )
    aid = paste["item"]["id"]

    corrected = await do_manage_dossier(
        json.dumps(
            {
                "action": "link_correct",
                "archive_id": aid,
                "person_id": pid,
                "situation_id": sid,
            }
        ),
        owner="alice",
    )
    assert corrected["item"]["person_id"] == pid

    plan = await do_manage_dossier(
        json.dumps(
            {
                "action": "plan_save",
                "person_id": pid,
                "situation_id": sid,
                "title": "Fan next steps",
                "summary": "Replace fan if error returns",
                "how_we_got_here": "Visit transcript + paste",
                "source_archive_ids": [aid],
                "origin": "paste",
            }
        ),
        owner="alice",
    )
    assert plan["plan"]["how_we_got_here"]
    assert aid in plan["plan"]["source_archive_ids"]

    dossier = await do_manage_dossier(
        json.dumps({"action": "dossier_get", "person_id": pid}), owner="alice"
    )
    assert set(dossier["person"]["labels"]) == {"friend", "client"}
    assert len(dossier["plans"]) == 1


@pytest.mark.asyncio
async def test_search_dossier_ae1(monkeypatch):
    db, engine = _mem_db()
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("core.database.SessionLocal", lambda: Session())
    from src.tools.dossier import do_manage_dossier
    from src.tools.archive import do_manage_archive
    from src.tools.dossier_search import do_search_dossier

    person = await do_manage_dossier(
        json.dumps({"action": "person_create", "display_name": "Fan Client", "labels": ["client"]}),
        owner="alice",
    )
    pid = person["person"]["id"]
    sit = await do_manage_dossier(
        json.dumps({"action": "situation_create", "person_id": pid, "title": "Fan"}),
        owner="alice",
    )
    sid = sit["situation"]["id"]
    arch = await do_manage_archive(
        json.dumps(
            {
                "action": "ingest",
                "source_tool": "plaud",
                "body": "If fan error returns, replace the fan.",
                "locator": "line:22",
                "person_id": pid,
                "situation_id": sid,
            }
        ),
        owner="alice",
    )
    aid = arch["item"]["id"]
    s = Session()
    _index_fts(s, access.get_archive_item(s, aid, "alice"))
    s.commit()
    s.close()

    await do_manage_dossier(
        json.dumps(
            {
                "action": "plan_save",
                "person_id": pid,
                "situation_id": sid,
                "title": "Repair plan",
                "summary": "Replace the fan if the error returns",
                "how_we_got_here": "In-home visit",
                "source_archive_ids": [aid],
            }
        ),
        owner="alice",
    )

    result = await do_search_dossier(
        json.dumps(
            {
                "action": "ask",
                "query": "fan error next steps",
                "person_id": pid,
                "situation_id": sid,
            }
        ),
        owner="alice",
    )
    assert result.get("ok")
    assert result.get("answer")
    kinds = {c["kind"] for c in result["citations"]}
    assert "plan" in kinds
    assert "archive" in kinds
    archive_cites = [c for c in result["citations"] if c["kind"] == "archive"]
    assert any(c.get("source_tool") == "plaud" for c in archive_cites)
    assert result.get("untrusted_content") is True
