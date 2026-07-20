"""Screw-map canvas zoom helpers — source contract (no browser)."""

from pathlib import Path

SRC = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "sysforge"
    / "static"
    / "js"
    / "screw-map-canvas.js"
).read_text(encoding="utf-8")


def test_canvas_exports_zoom_helpers():
    assert "export function zoomAtPoint" in SRC
    assert "export function screenToLetterbox" in SRC
    assert "export function letterboxToScreen" in SRC
    assert "MAX_ZOOM = 6" in SRC
    assert "MIN_ZOOM = 1" in SRC


def test_canvas_supports_note_markers_and_pan():
    assert 'data-kind="note"' in SRC
    assert "sysforge-sm-note-marker" in SRC
    assert "contextmenu" in SRC
    assert "wantsPan" in SRC
    assert "wheel" in SRC
