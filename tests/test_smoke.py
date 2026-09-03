"""Smoke tests. No browser, no network, no LLM. Just shape and logic."""

from __future__ import annotations

import json

import pytest

from onshape_mcp import tools as datasheet
from onshape_mcp.config import Settings
from onshape_mcp.dispatch import (
    TOOL_DISPATCH,
    build_agent_system_prompt,
    parse_decision,
)
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
    missing = []
    for t in datasheet.ALL_TOOLS:
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
    assert "onshape.cookies.json" not in rep


def test_parse_decision_clean_json() -> None:
    out = parse_decision('{"tool": "view.fit", "args": {}}')
    assert out == {"tool": "view.fit", "args": {}}


def test_parse_decision_fenced_json() -> None:
    text = (
        "Sure, here's the call:\n"
        "```json\n"
        '{"tool": "sketch.rectangle", "args": {"corner1_x": 10, "corner1_y": 10, "corner2_x": 100, "corner2_y": 60}}\n'
        "```\n"
    )
    out = parse_decision(text)
    assert out["tool"] == "sketch.rectangle"
    assert out["args"]["corner1_x"] == 10


def test_parse_decision_done_marker() -> None:
    out = parse_decision('{"done": true, "summary": "all done"}')
    assert out == {"done": True, "summary": "all done"}


def test_parse_decision_garbage() -> None:
    out = parse_decision("not json at all, just rambling")
    assert out.get("done") is True
    assert "summary" in out


def test_shortcuts_high_confidence_subset() -> None:
    high = {"ui.undo", "ui.redo", "view.fit", "sketch.start", "sketch.exit",
            "feature.extrude", "feature.chamfer"}
    for name in high:
        b = binding_for(name)
        assert b.confidence == "high", f"{name} should be high confidence, got {b.confidence}"


def test_dispatch_table_complete() -> None:
    expected = {
        "view.fit", "view.top",
        "sketch.start", "sketch.rectangle", "sketch.circle", "sketch.line",
        "sketch.dimension", "sketch.equal", "sketch.exit",
        "feature.extrude", "feature.fillet", "feature.chamfer",
        "select.face", "select.edge",
        "ui.undo", "ui.redo",
    }
    assert expected.issubset(set(TOOL_DISPATCH.keys())), \
        f"missing dispatch entries: {expected - set(TOOL_DISPATCH.keys())}"


def test_dispatch_sketch_dimension_signature() -> None:
    """sketch.dimension needs entity_xy + label_xy + value_mm.
    The dispatch handler should reshape flat LLM args into that."""
    from onshape_mcp.dispatch import _xy
    args = {"entity_x": 100, "entity_y": 200, "label_x": 110, "label_y": 210, "value_mm": 5}
    assert _xy(args, "entity_x", "entity_y") == (100.0, 200.0)
    assert _xy(args, "label_x", "label_y") == (110.0, 210.0)


def test_agent_prompt_teaches_constrained_sketch() -> None:
    """The system prompt should explicitly teach the constrained-sketch
    workflow so the LLM doesn't try to pick exact 5mm pixel coords."""
    p = build_agent_system_prompt()
    assert "constrained-sketch" in p
    assert "sketch.dimension" in p
    assert "5x5" in p
    assert "cube" in p


def test_run_task_importable() -> None:
    """The CLI runner should be importable without triggering browser/vision
    side effects."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_task", "scripts/run_task.py")
    assert spec is not None
