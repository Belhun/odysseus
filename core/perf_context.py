"""Context variables for performance event correlation."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional

request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "perf_request_id", default=None
)
run_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "perf_run_id", default=None
)
task_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "perf_task_id", default=None
)
session_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "perf_session_id", default=None
)
job_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "perf_job_id", default=None
)
workload_kind_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "perf_workload_kind", default=None
)
workload_name_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "perf_workload_name", default=None
)
operation_stack_var: contextvars.ContextVar[List[str]] = contextvars.ContextVar(
    "perf_operation_stack", default=None
)


def _stack() -> List[str]:
    stack = operation_stack_var.get()
    if stack is None:
        stack = []
        operation_stack_var.set(stack)
    return stack


def get_correlation() -> Dict[str, Any]:
    """Return current correlation fields for perf events."""
    out: Dict[str, Any] = {}
    for key, var in (
        ("request_id", request_id_var),
        ("run_id", run_id_var),
        ("task_id", task_id_var),
        ("session_id", session_id_var),
        ("job_id", job_id_var),
        ("workload_kind", workload_kind_var),
        ("workload_name", workload_name_var),
    ):
        val = var.get()
        if val is not None:
            out[key] = val
    stack = operation_stack_var.get()
    if stack:
        out["trace"] = list(stack)
    return out


def set_request_id(value: Optional[str]) -> contextvars.Token:
    return request_id_var.set(value)


def set_run_id(value: Optional[str]) -> contextvars.Token:
    return run_id_var.set(value)


def set_session_id(value: Optional[str]) -> contextvars.Token:
    return session_id_var.set(value)


def set_job_id(value: Optional[str]) -> contextvars.Token:
    return job_id_var.set(value)


def set_workload(kind: Optional[str], name: Optional[str]) -> None:
    workload_kind_var.set(kind)
    workload_name_var.set(name)


@contextmanager
def workload_context(
    kind: str,
    name: str,
    *,
    run_id: Optional[str] = None,
    task_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Iterator[None]:
    """Temporarily set workload + optional IDs for a scoped block."""
    tokens = []
    prev_kind = workload_kind_var.get()
    prev_name = workload_name_var.get()
    workload_kind_var.set(kind)
    workload_name_var.set(name)
    if run_id is not None:
        tokens.append(("run_id", run_id_var.set(run_id)))
    if task_id is not None:
        tokens.append(("task_id", task_id_var.set(task_id)))
    if session_id is not None:
        tokens.append(("session_id", session_id_var.set(session_id)))
    try:
        yield
    finally:
        workload_kind_var.set(prev_kind)
        workload_name_var.set(prev_name)
        for key, token in reversed(tokens):
            if key == "run_id":
                run_id_var.reset(token)
            elif key == "task_id":
                task_id_var.reset(token)
            elif key == "session_id":
                session_id_var.reset(token)


@contextmanager
def push_operation(name: str) -> Iterator[None]:
    stack = _stack()
    token = operation_stack_var.set(stack + [name])
    try:
        yield
    finally:
        operation_stack_var.reset(token)
