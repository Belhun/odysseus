"""Archive FTS search unit tests."""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.database import Base
from services.dossier import access
from services.dossier.archive_search import search_archive


def test_archive_fts_finds_keyword():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.execute(
        text(
            """
            CREATE VIRTUAL TABLE dossier_archive_fts USING fts5(
                body, item_id UNINDEXED, owner UNINDEXED
            )
            """
        )
    )
    item = access.create_archive_item(
        db, owner="alice", source_tool="plaud", body="modal jazz theory transcript"
    )
    db.execute(
        text("INSERT INTO dossier_archive_fts(body, item_id, owner) VALUES (:b,:i,:o)"),
        {"b": item.body, "i": item.id, "o": item.owner},
    )
    db.commit()
    hits = search_archive("jazz", owner="alice", db=db)
    assert hits and hits[0].item_id == item.id
    assert hits[0].source_tool == "plaud"
