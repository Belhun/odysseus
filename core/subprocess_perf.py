"""Shared helpers for subprocess performance events."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.perf_context import get_correlation, job_id_var, session_id_var
from core.perf_emit import emit


def emit_spawned(
    *,
    spawn_path: str,
    tool: str,
    child_pid: int,
    command_preview: str = "",
    job_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    fields = {
        "spawn_path": spawn_path,
        "tool": tool,
        "child_pid": child_pid,
        "command_preview": (command_preview or "")[:200],
    }
    if job_id:
        fields["job_id"] = job_id
    if extra:
        fields.update(extra)
    emit("subprocess.spawned", **fields)


def emit_completed(
    *,
    child_pid: int,
    duration_ms: float,
    exit_code: int = 0,
    timed_out: bool = False,
    stdout_chars: int = 0,
    stderr_chars: int = 0,
    job_id: Optional[str] = None,
    tool: Optional[str] = None,
) -> None:
    emit(
        "subprocess.completed",
        child_pid=child_pid,
        duration_ms=round(duration_ms, 2),
        exit_code=exit_code,
        timed_out=timed_out,
        stdout_chars=stdout_chars,
        stderr_chars=stderr_chars,
        job_id=job_id,
        tool=tool,
    )


class SubprocessTimer:
    """Track wall time for a subprocess invocation."""

    def __init__(self, child_pid: int, tool: str, spawn_path: str, command_preview: str = ""):
        self.child_pid = child_pid
        self.tool = tool
        self.spawn_path = spawn_path
        self.command_preview = command_preview
        self._t0 = time.perf_counter()
        emit_spawned(
            spawn_path=spawn_path,
            tool=tool,
            child_pid=child_pid,
            command_preview=command_preview,
            job_id=job_id_var.get(),
        )

    def complete(
        self,
        exit_code: int = 0,
        timed_out: bool = False,
        stdout_chars: int = 0,
        stderr_chars: int = 0,
    ) -> None:
        emit_completed(
            child_pid=self.child_pid,
            duration_ms=(time.perf_counter() - self._t0) * 1000,
            exit_code=exit_code,
            timed_out=timed_out,
            stdout_chars=stdout_chars,
            stderr_chars=stderr_chars,
            job_id=job_id_var.get(),
            tool=self.tool,
        )
