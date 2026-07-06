"""Instrumented asyncio.to_thread wrapper."""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import Any, Callable, TypeVar

from core.perf_context import get_correlation, push_operation
from core.perf_emit import emit

T = TypeVar("T")

_original_to_thread = asyncio.to_thread
_patched = False


def _func_label(func: Callable, /) -> str:
    if inspect.ismethod(func):
        return f"{func.__self__.__class__.__name__}.{func.__name__}"
    mod = getattr(func, "__module__", "") or ""
    name = getattr(func, "__name__", repr(func))
    return f"{mod}.{name}" if mod else name


async def to_thread(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Drop-in replacement for asyncio.to_thread with perf events."""
    label = _func_label(func)
    t0 = time.perf_counter()
    emit("thread.work.started", func=label)
    with push_operation(f"to_thread:{label}"):
        try:
            result = await _original_to_thread(func, *args, **kwargs)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            emit("thread.work.completed", func=label, duration_ms=duration_ms, status="ok")
            return result
        except Exception as exc:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            emit(
                "thread.work.completed",
                func=label,
                duration_ms=duration_ms,
                status="error",
                error=str(exc),
            )
            raise


def install() -> None:
    """Patch asyncio.to_thread globally (idempotent)."""
    global _patched
    if _patched:
        return
    asyncio.to_thread = to_thread  # type: ignore[attr-defined]
    _patched = True
