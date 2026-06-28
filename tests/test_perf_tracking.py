"""Tests for performance tracking core modules."""

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]

# Stub core package so perf modules load without pulling full app deps.
if "core" not in sys.modules:
    sys.modules["core"] = types.ModuleType("core")
_fake_constants = types.ModuleType("core.constants")
_fake_constants.DATA_DIR = tempfile.gettempdir()
sys.modules["core.constants"] = _fake_constants


def _load_module(name: str, rel_path: str):
    path = _ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


perf_context = _load_module("perf_context_test", "core/perf_context.py")
sys.modules["core.perf_context"] = perf_context
perf_emit = _load_module("perf_emit_test", "core/perf_emit.py")

get_correlation = perf_context.get_correlation
request_id_var = perf_context.request_id_var
set_request_id = perf_context.set_request_id
workload_context = perf_context.workload_context
emit = perf_emit.emit
perf_enabled = perf_emit.perf_enabled
tail_events = perf_emit.tail_events


class PerfEmitTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._sink = os.path.join(self._tmpdir, "perf.jsonl")
        patcher = patch.object(perf_emit, "get_sink_path", return_value=self._sink)
        self.addCleanup(patcher.stop)
        patcher.start()
        patcher2 = patch.dict(os.environ, {"ODYSSEUS_PERF": "true"})
        self.addCleanup(patcher2.stop)
        patcher2.start()

    def test_emit_writes_jsonl(self):
        token = set_request_id("req-abc")
        try:
            emit("test.event", foo="bar")
        finally:
            request_id_var.reset(token)
        with open(self._sink, encoding="utf-8") as f:
            line = json.loads(f.readline())
        self.assertEqual(line["event"], "test.event")
        self.assertEqual(line["request_id"], "req-abc")
        self.assertEqual(line["foo"], "bar")
        self.assertEqual(line["v"], 1)

    def test_tail_events_ring(self):
        emit("alpha.one")
        emit("alpha.two")
        rows = tail_events(10, event_prefix="alpha.")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["event"].startswith("alpha.") for r in rows))

    def test_perf_disabled(self):
        with patch.dict(os.environ, {"ODYSSEUS_PERF": "0"}):
            self.assertFalse(perf_enabled())
            emit("should.not.appear")
        self.assertFalse(os.path.exists(self._sink))


class PerfContextTests(unittest.TestCase):
    def test_workload_context(self):
        with workload_context("bg_loop", "email.poller"):
            corr = get_correlation()
        self.assertEqual(corr.get("workload_kind"), "bg_loop")
        self.assertEqual(corr.get("workload_name"), "email.poller")
        self.assertNotIn("workload_kind", get_correlation())


if __name__ == "__main__":
    unittest.main()
