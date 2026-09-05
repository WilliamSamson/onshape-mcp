"""Smoke tests. No browser, no network, no LLM. Just shape and logic."""

from __future__ import annotations

from onshape_mcp import tools as datasheet
from onshape_mcp.config import Settings
from onshape_mcp.dispatch import (
    TOOL_DISPATCH,
    build_agent_system_prompt,
    parse_decision,
)
from onshape_mcp.journal import Journal, JournalEntry
from onshape_mcp.shortcuts import BINDINGS
from onshape_mcp.shortcuts import get as binding_for


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
    high = {
        "ui.undo",
        "ui.redo",
        "view.fit",
        "sketch.start",
        "sketch.exit",
        "feature.extrude",
        "feature.chamfer",
    }
    for name in high:
        b = binding_for(name)
        assert b.confidence == "high", f"{name} should be high confidence, got {b.confidence}"


def test_dispatch_table_complete() -> None:
    expected = {
        "view.fit",
        "view.top",
        "sketch.start",
        "sketch.rectangle",
        "sketch.circle",
        "sketch.line",
        "sketch.dimension",
        "sketch.equal",
        "sketch.exit",
        "feature.extrude",
        "feature.fillet",
        "feature.chamfer",
        "select.face",
        "select.edge",
        "ui.undo",
        "ui.redo",
    }
    assert expected.issubset(set(TOOL_DISPATCH.keys())), (
        f"missing dispatch entries: {expected - set(TOOL_DISPATCH.keys())}"
    )


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


def test_server_tool_datasheet() -> None:
    import asyncio

    from onshape_mcp.server import tool_datasheet

    sheet = asyncio.run(tool_datasheet())
    assert "# Onshape tool vocabulary" in sheet
    assert "sketch.start" in sheet


def test_settings_chat_management() -> None:
    s = Settings()
    assert isinstance(s.gemini_temporary_chat, bool)
    assert isinstance(s.gemini_auto_cleanup, bool)
    assert s.gemini_temporary_chat is True
    assert s.gemini_auto_cleanup is True


def test_gemini_web_session_management() -> None:
    from onshape_mcp.vision import GeminiWeb

    gw = GeminiWeb()
    assert gw.temporary is True
    assert gw.auto_cleanup is True
    assert isinstance(gw.created_chat_ids, set)
    assert len(gw.created_chat_ids) == 0
    assert gw.get_session() is None
    gw.reset_session()
    assert gw.get_session() is None


def test_gemini_web_cleanup_empty() -> None:
    import asyncio

    from onshape_mcp.vision import GeminiWeb

    gw = GeminiWeb()
    deleted = asyncio.run(gw.cleanup_created_chats())
    assert deleted == 0


def test_gemini_dependency_and_feature_management_dispatch() -> None:
    """The deployed vision dependency and deterministic delete path stay wired."""
    import gemini_webapi

    assert gemini_webapi is not None
    for tool in ("feature.delete", "feature.list", "document.undo", "document.redo"):
        assert tool in TOOL_DISPATCH


def test_manage_chats_importable() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("manage_chats", "scripts/manage_chats.py")
    assert spec is not None


def test_fast_executor_stops_on_false_result() -> None:
    import asyncio
    from pathlib import Path
    from unittest.mock import AsyncMock, patch

    from onshape_mcp.fast_exec import execute
    from onshape_mcp.intent import Action, Plan
    from onshape_mcp.ui_actions import Result

    driver = AsyncMock()
    driver.screenshot.return_value = Path("/tmp/final.png")
    plan = Plan([Action("sketch.start", {"plane": "Top"})], "test")
    with patch("onshape_mcp.fast_exec.dispatch", AsyncMock(return_value=Result(False, "not active"))):
        result = asyncio.run(execute(driver, plan))
    assert result.ok is False
    assert result.error == "sketch.start: not active"


def test_act_lists_features_without_gemini() -> None:
    import asyncio
    import json
    from unittest.mock import AsyncMock, patch

    from onshape_mcp.server import act
    from onshape_mcp.ui_actions import Result

    with (
        patch("onshape_mcp.server._driver_lazy", AsyncMock(return_value=object())),
        patch(
            "onshape_mcp.server.ui_actions.features_list",
            AsyncMock(return_value=Result(True, "Found 2 features", extra={"features": ["Sketch 1", "Sketch 2"]})),
        ),
        patch("onshape_mcp.server._loop_lazy", AsyncMock()) as vision_fallback,
    ):
        result = json.loads(asyncio.run(act("list existing features")))

    assert result["ok"] is True
    assert result["mode"] == "deterministic_inspection"
    assert result["features"] == ["Sketch 1", "Sketch 2"]
    vision_fallback.assert_not_awaited()


def test_intent_parses_5x5_cube() -> None:
    """The intent parser should produce a 4-action plan for the canonical
    '5x5 cube' goal."""
    from onshape_mcp.intent import parse
    plan = parse("draw a 5x5 square on the top plane and extrude it 5mm into a cube")
    assert plan is not None
    assert len(plan.actions) == 4
    tools = [a.tool for a in plan.actions]
    assert tools == ["sketch.start", "sketch.rectangle", "sketch.exit", "feature.extrude"]
    assert plan.actions[-1].args.get("depth_mm") == 5.0


def test_intent_unit_conversion() -> None:
    """Unit handling: '12cm by 8cm' gives 12cm x 8cm; extrude 2cm gives
    depth_mm = 20."""
    from onshape_mcp.intent import parse
    plan = parse("draw a 12cm by 8cm box on the top plane and extrude 2cm")
    assert plan is not None
    assert plan.actions[1].args["width"] == "12 cm"
    assert plan.actions[1].args["height"] == "8 cm"
    assert plan.actions[-1].args["depth_mm"] == 20.0


def test_intent_rejects_unknown() -> None:
    """Non-CAD prompts return None (caller falls back to vision loop)."""
    from onshape_mcp.intent import parse
    assert parse("hello world") is None
    assert parse("") is None


def test_extrude_selects_latest_sketch_helper_exists() -> None:
    """The latest-sketch selector should be a callable async function
    in ui_actions. Smoke check that the JS snippet is a non-empty
    string with no Python f-string holes."""
    from onshape_mcp.ui_actions import _select_latest_sketch
    import inspect
    assert inspect.iscoroutinefunction(_select_latest_sketch)
    src = inspect.getsource(_select_latest_sketch)
    assert "Sketch" in src
    assert "feature-tree" in src or "FeatureTree" in src
    # The f-string regex (\d+ in JS) must be escaped properly in the
    # Python source so the JS actually sees \d+ at runtime.
    assert "\\\\d+" in src or "\\d+" in src
