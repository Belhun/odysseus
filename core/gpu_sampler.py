"""Ollama and GPU performance sampling."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from typing import Any, Dict, List, Optional

import httpx

from core.perf_emit import emit, perf_enabled

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_latest_gpu: Dict[str, Any] = {}
_latest_ollama: Dict[str, Any] = {}


def _ollama_base() -> str:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
    if not host.startswith("http"):
        host = f"http://{host}"
    return host


async def fetch_ollama_ps() -> Dict[str, Any]:
    url = f"{_ollama_base()}/api/ps"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return {}
            data = resp.json()
            models = data.get("models") or []
            total_vram = sum(int(m.get("size_vram") or 0) for m in models)
            payload = {
                "models": [
                    {
                        "name": m.get("name"),
                        "size_vram": m.get("size_vram"),
                        "processor": m.get("processor"),
                    }
                    for m in models
                ],
                "model_count": len(models),
                "total_vram": total_vram,
            }
            emit("ollama.ps", **payload)
            return payload
    except Exception as e:
        logger.debug("ollama /api/ps failed: %s", e)
        return {}


def _nvidia_smi_sample() -> Dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if result.returncode != 0:
            return {}
        gpus = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 5:
                continue
            gpus.append(
                {
                    "index": int(parts[0]),
                    "name": parts[1],
                    "util_pct": float(parts[2]) if parts[2] not in ("[N/A]", "") else None,
                    "used_mb": float(parts[3]) if parts[3] not in ("[N/A]", "") else None,
                    "total_mb": float(parts[4]) if parts[4] not in ("[N/A]", "") else None,
                }
            )
        proc_result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
        processes = []
        if proc_result.returncode == 0:
            for line in proc_result.stdout.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue
                processes.append(
                    {
                        "pid": int(parts[0]) if parts[0].isdigit() else parts[0],
                        "name": parts[1],
                        "used_mb": float(parts[2]) if re.match(r"[\d.]+", parts[2]) else parts[2],
                    }
                )
        payload = {"source": "nvidia-smi", "gpus": gpus, "processes": processes}
        emit("gpu.sample", **payload)
        return payload
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.debug("nvidia-smi failed: %s", e)
        return {}


def get_latest_gpu_sample() -> Dict[str, Any]:
    return dict(_latest_gpu)


def get_latest_ollama_ps() -> Dict[str, Any]:
    return dict(_latest_ollama)


async def _loop(interval: float) -> None:
    global _latest_gpu, _latest_ollama
    while True:
        try:
            if perf_enabled():
                _latest_ollama = await fetch_ollama_ps()
                _latest_gpu = await asyncio.to_thread(_nvidia_smi_sample)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("gpu/ollama sampler: %s", e)
        await asyncio.sleep(interval)


def start_gpu_ollama_sampler(interval: float = 30.0) -> asyncio.Task:
    global _task
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(_loop(interval), name="perf.gpu_ollama_sampler")
    return _task


def stop_gpu_ollama_sampler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None


async def sample_ollama_on_llm() -> None:
    """Lightweight hook around LLM calls."""
    if perf_enabled():
        await fetch_ollama_ps()
