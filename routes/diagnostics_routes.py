"""Diagnostics routes — /api/db/stats, /api/rag/stats, /api/test/youtube, /api/test-research."""

import logging
import os
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Form, Request

from services.youtube.youtube_handler import extract_youtube_id, extract_transcript_async
from core.constants import DEFAULT_HOST, DATA_DIR
from core.middleware import require_admin

logger = logging.getLogger(__name__)


def setup_diagnostics_routes(
    rag_manager,
    rag_available: bool,
    research_handler,
    memory_vector=None,
) -> APIRouter:
    router = APIRouter(tags=["diagnostics"])

    @router.get("/api/diagnostics/services")
    async def get_service_health(request: Request) -> Dict[str, Any]:
        """Consolidated degraded-state report for ChromaDB, SearXNG, email,
        ntfy, and provider endpoints. Non-intrusive probes — safe to poll."""
        require_admin(request)
        from src.service_health import collect_service_health
        return await collect_service_health(rag_manager, memory_vector)

    @router.get("/api/diagnostics/logs")
    async def get_diagnostics_logs(request: Request, limit: int = 200) -> Dict[str, Any]:
        require_admin(request)
        limit = max(1, min(limit, 1000))
        try:
            log_file = os.path.join(DATA_DIR, "logs", "app.log")
            if not os.path.exists(log_file):
                return {"status": "success", "logs": []}

            # Safe tail read of the log file (max 5MB via rotation)
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()

            tail_lines = lines[-limit:] if len(lines) > limit else lines
            tail_lines = [line.rstrip('\r\n') for line in tail_lines]

            return {
                "status": "success",
                "logs": tail_lines
            }
        except Exception as e:
            logger.error(f"Diagnostics logs retrieval error: {e}")
            raise HTTPException(500, f"Failed to retrieve logs: {str(e)}")

    @router.get("/api/diagnostics/perf")
    async def get_perf_events(
        request: Request,
        limit: int = 100,
        event_prefix: str = "",
    ) -> Dict[str, Any]:
        """Tail recent performance events from perf.jsonl ring buffer."""
        require_admin(request)
        from core.perf_emit import tail_events, read_file_tail, get_sink_path, perf_enabled
        limit = max(1, min(limit, 1000))
        prefix = event_prefix.strip() or None
        events = tail_events(limit, event_prefix=prefix)
        if not events:
            events = read_file_tail(limit)
            if prefix:
                events = [e for e in events if str(e.get("event", "")).startswith(prefix)]
        return {
            "status": "success",
            "enabled": perf_enabled(),
            "sink_path": get_sink_path(),
            "count": len(events),
            "events": events,
        }

    @router.get("/api/diagnostics/subprocesses")
    async def get_subprocess_diagnostics(request: Request) -> Dict[str, Any]:
        """Running background jobs and recent subprocess events."""
        require_admin(request)
        from core.perf_emit import tail_events
        from src.bg_jobs import refresh
        jobs_map = refresh()
        running = [j for j in jobs_map.values() if j.get("status") == "running"]
        recent = tail_events(50, event_prefix="subprocess.")
        return {"status": "success", "bg_jobs_running": running, "recent_subprocess_events": recent}

    @router.get("/api/diagnostics/containers")
    async def get_container_diagnostics(request: Request) -> Dict[str, Any]:
        """Latest Docker container stats samples."""
        require_admin(request)
        from core.container_stats import get_latest_container_samples
        from core.perf_emit import tail_events
        samples = get_latest_container_samples()
        if not samples:
            samples = [
                e for e in tail_events(100, event_prefix="container.")
            ]
        return {"status": "success", "samples": samples}

    @router.get("/api/diagnostics/gpu")
    async def get_gpu_diagnostics(request: Request) -> Dict[str, Any]:
        """Latest GPU and Ollama /api/ps snapshots."""
        require_admin(request)
        from core.gpu_sampler import get_latest_gpu_sample, get_latest_ollama_ps
        return {
            "status": "success",
            "gpu": get_latest_gpu_sample(),
            "ollama_ps": get_latest_ollama_ps(),
        }

    @router.get("/api/diagnostics/system-snapshot")
    async def get_system_snapshot(request: Request) -> Dict[str, Any]:
        """Current in-process system snapshot from the perf sampler."""
        require_admin(request)
        from core.process_sampler import get_system_snapshot
        return {"status": "success", "snapshot": get_system_snapshot()}

    @router.get("/api/diagnostics/active-runs")
    async def get_active_runs(request: Request) -> Dict[str, Any]:
        """Currently executing task runs with live resource peaks."""
        require_admin(request)
        from core.perf_runs import active_run_summaries
        return {"status": "success", "active_runs": active_run_summaries()}

    @router.get("/api/db/stats")
    async def get_database_stats(request: Request) -> Dict[str, Any]:
        require_admin(request)
        try:
            from core.database import get_detailed_stats
            return get_detailed_stats()
        except Exception as e:
            logger.error(f"DB stats error: {e}")
            raise HTTPException(500, "Failed to retrieve database statistics")

    @router.get("/api/rag/stats")
    async def get_rag_stats(request: Request) -> Dict[str, Any]:
        require_admin(request)
        if rag_available and rag_manager:
            return rag_manager.get_stats()
        return {"error": "RAG system not available"}

    @router.get("/api/test/youtube")
    async def test_youtube(request: Request, url: str) -> Dict[str, Any]:
        require_admin(request)
        try:
            video_id = extract_youtube_id(url)
            if not video_id:
                return {"error": "Invalid YouTube URL"}

            data = await extract_transcript_async(url, video_id)
            return {
                "video_id": video_id,
                "transcript_success": data.get("success", False),
                "transcript_length": len(data.get("transcript", "")) if data.get("success") else 0,
                "transcript_preview": (data.get("transcript", "")[:500] + "...")
                    if data.get("success") and len(data.get("transcript", "")) > 500
                    else data.get("transcript", ""),
                "error": data.get("error") if not data.get("success") else None,
            }
        except Exception as e:
            return {"error": str(e)}

    @router.post("/api/test-research")
    async def test_research(request: Request, query: str = Form("What is machine learning?")) -> Dict[str, Any]:
        require_admin(request)
        try:
            endpoint = f"http://{DEFAULT_HOST}:8000/v1/chat/completions"
            model = "gpt-oss-120b"
            result = await research_handler.call_research_service(query, endpoint, model)
            return {
                "status": "success",
                "query": query,
                "result_preview": result[:200] + "..." if len(result) > 200 else result,
                "result_length": len(result),
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "query": query}

    return router
