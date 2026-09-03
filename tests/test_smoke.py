"""Smoke tests. No browser, no network, no LLM. Just shape and logic."""

from __future__ import annotations

import json

import pytest

from onshape_mcp import tools as datasheet
from onshape_mcp.config import Settings
from onshape_mcp.journal import Journal, JournalEntry
from onshape_mcp.shortcuts import BINDINGS, get as binding_for


def test_datasheet_has_tools() -> None:
    assert len(datasheet.ALL_TOOLS) >= 20
    for t in datasheet.ALL_TOOLS:
        assert t.name
        assert t.purpose
        assert t.status in {"planned", "stub", "working"}


def test_datasheet_lookup() -> None:
    s = datasheet.lookup("feature.extrude")
    assert s.purpose
    assert "sketch.active=false" in s.requires


def test_every_datasheet_tool_has_a_binding() -> None:
    """If a tool is in the datasheet, it should be in shortcuts too. If not,
    the agent will try to call it and crash."""
    missing = []
    for t in datasheet.ALL_TOOLS:
        # We only require bindings for tools that have a real UI presence.
        # Doc/meta + assembly.pattern are M2.
        requires_binding = not t.name.startswith("doc.")
        if requires_binding and t.name not in BINDINGS:
            missing.append(t.name)
    assert not missing, f"datasheet tools without shortcuts binding: {missing}"


def test_journal_round_trip(tmp_path) -> None:
    j = Journal(path=tmp_path / "t.journal.jsonl")
    j.append(JournalEntry.new("screenshot", {"name": "a.png"}))
    j.append(JournalEntry.new("ui.undo", {}))
    tail = j.tail()
    assert len(tail) == 2
    assert tail[0]["tool"] == "screenshot"
    assert tail[1]["tool"] == "ui.undo"


def test_settings_redacts_paths() -> None:
    s = Settings()
    rep = repr(s)
    assert "playwright-profile" not in rep
    assert "gemini.cookies.json" not in rep


def test_parse_decision_clean_json() -> None:
    from onshape_mcp.server import _parse_decision
    out = _parse_decision('{"tool": "view.fit", "args": {}}')
    assert out == {"tool": "view.fit", "args": {}}


def test_parse_decision_fenced_json() -> None:
    from onshape_mcp.server import _parse_decision
    text = (
        "Sure, here's the call:\n"
        "```json\n"
        '{"tool": "sketch.rectangle", "args": {"corner1_x": 10, "corner1_y": 10, "corner2_x": 100, "corner2_y": 60}}\n'
        "```\n"
    )
    out = _parse_decision(text)
    assert out["tool"] == "sketch.rectangle"
    assert out["args"]["corner1_x"] == 10


def test_parse_decision_done_marker() -> None:
    from onshape_mcp.server import _parse_decision
    out = _parse_decision('{"done": true, "summary": "all done"}')
    assert out == {"done": True, "summary": "all done"}


def test_parse_decision_garbage() -> None:
    from onshape_mcp.server import _parse_decision
    out = _parse_decision("not json at all, just rambling")
    # Falls back to a done-with-error summary so the loop terminates.
    assert out.get("done") is True
    assert "summary" in out


def test_shortcuts_high_confidence_subset() -> None:
    """The tools we just implemented should be marked high confidence OR
    explicitly flagged medium with a note. Spot-check the core set."""
    high = {"ui.undo", "ui.redo", "view.fit", "sketch.start", "sketch.exit",
            "feature.extrude", "feature.chamfer"}
    for name in high:
        b = binding_for(name)
        assert b.confidence == "high", f"{name} should be high confidence, got {b.confidence}"


def test_dispatch_table_complete() -> None:
    """Every tool the LLM can call must have a dispatch entry."""
    from onshape_mcp.server import TOOL_DISPATCH
    expected = {
        "view.fit", "view.top",
        "sketch.start", "sketch.rectangle", "sketch.circle", "sketch.line", "sketch.exit",
        "feature.extrude", "feature.fillet", "feature.chamfer",
        "select.face", "select.edge",
        "ui.undo", "ui.redo",
    }
    assert expected.issubset(set(TOOL_DISPATCH.keys())), \
        f"missing dispatch entries: {expected - set(TOOL_DISPATCH.keys())}"
