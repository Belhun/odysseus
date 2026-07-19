"""manage_dossier unit coverage (AE2/AE3/AE4 data path)."""
import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base


@pytest.mark.asyncio
async def test_paste_plan_and_labels(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr("core.database.SessionLocal", lambda: Session())
    from src.tools.dossier import do_manage_dossier
    from src.tools.archive import do_manage_archive

    person = await do_manage_dossier(
        json.dumps({"action": "person_create", "display_name": "Friend", "labels": ["friend"]}),
        owner="alice",
    )
    pid = person["person"]["id"]
    arch = await do_manage_archive(
        json.dumps(
            {
                "action": "ingest",
                "source_tool": "paste",
                "body": "AI said: feed dogs twice daily",
                "person_id": pid,
            }
        ),
        owner="alice",
    )
    plan = await do_manage_dossier(
        json.dumps(
            {
                "action": "plan_save",
                "person_id": pid,
                "title": "Dog feeding",
                "summary": "Feed twice daily",
                "how_we_got_here": "Pasted from other AI",
                "source_archive_ids": [arch["item"]["id"]],
                "origin": "paste",
            }
        ),
        owner="alice",
    )
    assert plan["ok"]
    assert plan["plan"]["origin"] == "paste"
