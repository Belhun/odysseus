"""Email Local Sync must run while the Odysseus UI is open.

Browser heartbeats and /api/email/local/* polls never leave a quiet window, so
gating sync_local_emails on idle left the task queued forever.
"""

import asyncio

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


def _setup_db(tmp_path, monkeypatch):
    import core.database as cd

    base = declarative_base()

    class ScheduledTask(base):
        __tablename__ = "scheduled_tasks"

        id = Column(String, primary_key=True)
        owner = Column(String)
        name = Column(String)
        task_type = Column(String, default="action")
        action = Column(String)
        status = Column(String, default="active")

    class TaskRun(base):
        __tablename__ = "task_runs"

        id = Column(String, primary_key=True)
        task_id = Column(String)
        started_at = Column(DateTime)
        finished_at = Column(DateTime)
        status = Column(String)
        result = Column(Text)
        error = Column(Text)
        model = Column(String)

    engine = create_engine(f"sqlite:///{tmp_path / 'tasks.db'}")
    base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(cd, "SessionLocal", session_local)
    monkeypatch.setattr(cd, "ScheduledTask", ScheduledTask)
    monkeypatch.setattr(cd, "TaskRun", TaskRun)
    return session_local, ScheduledTask, TaskRun


def test_sync_local_emails_skips_foreground_gate(tmp_path, monkeypatch):
    session_local, ScheduledTask, _TaskRun = _setup_db(tmp_path, monkeypatch)
    db = session_local()
    db.add(ScheduledTask(
        id="sync-task",
        owner="alice",
        name="Email Local Sync",
        task_type="action",
        action="sync_local_emails",
        status="active",
    ))
    db.add(ScheduledTask(
        id="llm-task",
        owner="alice",
        name="Daily Brief",
        task_type="action",
        action="daily_brief",
        status="active",
    ))
    db.commit()
    db.close()

    from src.task_scheduler import TaskScheduler

    scheduler = TaskScheduler.__new__(TaskScheduler)
    assert scheduler._task_gates_on_foreground("sync-task") is False
    assert scheduler._task_gates_on_foreground("llm-task") is True


def test_stop_background_skips_ungated_sync_task(tmp_path, monkeypatch):
    session_local, ScheduledTask, TaskRun = _setup_db(tmp_path, monkeypatch)
    db = session_local()
    db.add(ScheduledTask(
        id="sync-task",
        owner="alice",
        name="Email Local Sync",
        task_type="action",
        action="sync_local_emails",
        status="active",
    ))
    db.add(TaskRun(
        id="run-1",
        task_id="sync-task",
        status="running",
        result="Starting…",
    ))
    db.commit()
    db.close()

    from src.task_scheduler import TaskScheduler

    async def drive():
        scheduler = TaskScheduler.__new__(TaskScheduler)
        scheduler._executing = {"sync-task"}
        scheduler._executing_lock = asyncio.Lock()
        scheduler._foreground_gated = set()  # ungated — like sync_local_emails
        scheduler._task_handles = {}

        stopped = await scheduler.stop_background_tasks_for_foreground(
            reason="browser heartbeat",
        )
        assert stopped == 0

        db2 = session_local()
        try:
            run = db2.query(TaskRun).filter(TaskRun.id == "run-1").first()
            assert run.status == "running"
        finally:
            db2.close()

        scheduler._foreground_gated.add("sync-task")
        stopped = await scheduler.stop_background_tasks_for_foreground(
            reason="browser heartbeat",
        )
        assert stopped >= 1
        db3 = session_local()
        try:
            run = db3.query(TaskRun).filter(TaskRun.id == "run-1").first()
            assert run.status == "aborted"
        finally:
            db3.close()

    asyncio.run(drive())
