"""Source contracts and inline math for the finance web-steal UI."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_JS = _REPO / "integrations" / "finance" / "static" / "js" / "index.js"
_CSS = _REPO / "static" / "style.css"
_HAS_NODE = shutil.which("node") is not None


def _js_source() -> str:
    return _JS.read_text(encoding="utf-8")


def test_finance_ui_has_privacy_overflow_paste_and_rules_surfaces():
    js = _js_source()
    css = _CSS.read_text(encoding="utf-8")
    assert "odysseus-finance-privacy" in js
    assert "finance-privacy-on" in css
    assert "filter: blur" in css
    assert "finance-density-compact" in css
    assert "{ id: 'rules', label: 'Rules', overflow: true }" in js
    assert "id: 'reports'" in js
    assert "/import/preview-text" in js
    assert "finance-import-paste" in js
    assert "Preview paste" in js
    assert "async function _renderRules" in js
    assert "finance-report-cards" in js
    assert "_renderUpcomingAndSubscriptions" in js
    assert "evalFinanceAmount" in js
    assert "finance-overlay" in js


@pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")
def test_eval_finance_amount_inline_math():
    js = _js_source()
    match = re.search(
        r"export function evalFinanceAmount\(raw\) \{.*?\n\}",
        js,
        flags=re.S,
    )
    assert match, "evalFinanceAmount export is missing"
    script = f"""
    {match.group(0).replace('export function', 'function', 1)}
    const cases = {{
      sum: evalFinanceAmount('12.50+3.20'),
      plain: evalFinanceAmount('12.50'),
      empty: evalFinanceAmount(''),
      bad: evalFinanceAmount('alert(1)'),
    }};
    console.log(JSON.stringify(cases));
    """
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        capture_output=True,
        text=True,
        cwd=str(_REPO),
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    assert data["sum"] == 1570
    assert data["plain"] == 1250
    assert data["empty"] is None
    assert data["bad"] is None
