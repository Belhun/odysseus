"""Background workload instrumentation helpers."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

from core.perf_context import workload_context
from core.perf_emit import emit

F = TypeVar("F", bound=Callable[..., Any])


def instrument_bg_loop(kind: str, name: str) -> Callable[[F], F]:
    """Decorator for async loop bodies — emits bg.work.completed each iteration."""

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            with workload_context(kind, name):
                emit("bg.work.started", workload_kind=kind, workload_name=name)
                try:
                    result = await fn(*args, **kwargs)
                    emit(
                        "bg.work.completed",
                        workload_kind=kind,
                        workload_name=name,
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                        status="ok",
                    )
                    return result
                except Exception as exc:
                    emit(
                        "bg.work.completed",
                        workload_kind=kind,
                        workload_name=name,
                        duration_ms=round((time.perf_counter() - t0) * 1000, 2),
                        status="error",
                        error=str(exc),
                    )
                    raise

        return wrapper  # type: ignore

    return decorator


def emit_task_lifecycle(
    phase: str,
    *,
    run_id: str,
    task_id: str,
    task_name: str,
    task_type: str,
    action: str = "",
    trigger: str = "",
    duration_ms: float | None = None,
    error: str | None = None,
    **extra: Any,
) -> None:
    emit(
        "task.run.lifecycle",
        phase=phase,
        run_id=run_id,
        task_id=task_id,
        task_name=task_name,
        task_type=task_type,
        action=action,
        trigger=trigger,
        duration_ms=duration_ms,
        error=error,
        **extra,
    )
