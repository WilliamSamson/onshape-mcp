"""Shared dispatch logic. The LLM calls a tool by name with flat kwargs;
we reshape them to the function signatures in ui_actions.

Used by both the MCP server (act tool) and the run_task CLI so they
can't drift apart.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import ui_actions
from .driver import OnshapeDriver


def parse_decision(text: str) -> dict[str, Any]:
    """Pull a JSON object out of a Gemini reply. Tolerant of markdown fences."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    else:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        candidate = brace.group(0) if brace else text
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return {"done": True, "summary": f"Could not parse decision: {text[:200]}"}


def _xy(args: dict[str, Any], x_key: str, y_key: str) -> tuple[float, float]:
    return (float(args[x_key]), float(args[y_key]))


# Tool name -> async fn(d, args) that calls the right ui_action.
TOOL_DISPATCH: dict[str, Any] = {
    "view.fit": lambda d, a: ui_actions.view_fit(d),
    "view.top": lambda d, a: ui_actions.view_top(d),
    "sketch.start": lambda d, a: ui_actions.sketch_start(
        d,
        (a["plane_x"], a["plane_y"]) if "plane_x" in a and "plane_y" in a else None,
    ),
    "sketch.rectangle": lambda d, a: ui_actions.sketch_rectangle(
        d, _xy(a, "corner1_x", "corner1_y"), _xy(a, "corner2_x", "corner2_y")
    ),
    "sketch.circle": lambda d, a: ui_actions.sketch_circle(
        d, _xy(a, "center_x", "center_y"), float(a["radius_px"])
    ),
    "sketch.line": lambda d, a: ui_actions.sketch_line(
        d, _xy(a, "p1_x", "p1_y"), _xy(a, "p2_x", "p2_y")
    ),
    "sketch.dimension": lambda d, a: ui_actions.sketch_dimension(
        d,
        _xy(a, "entity_x", "entity_y"),
        _xy(a, "label_x", "label_y"),
        float(a["value_mm"]),
    ),
    "sketch.equal": lambda d, a: ui_actions.sketch_equal(
        d, *[(a[f"x{i}"], a[f"y{i}"]) for i in range(int(a.get("n", 2)))]
    ),
    "sketch.exit": lambda d, a: ui_actions.sketch_exit(d),
    "feature.extrude": lambda d, a: ui_actions.feature_extrude(d, a.get("depth_mm")),
    "feature.fillet": lambda d, a: ui_actions.feature_fillet(d, a.get("radius_mm")),
    "feature.chamfer": lambda d, a: ui_actions.feature_chamfer(d, a.get("distance_mm")),
    "select.face": lambda d, a: ui_actions.select_face(d, float(a["x"]), float(a["y"])),
    "select.edge": lambda d, a: ui_actions.select_edge(d, float(a["x"]), float(a["y"])),
    "ui.undo": lambda d, a: ui_actions.undo(d),
    "ui.redo": lambda d, a: ui_actions.redo(d),
}


async def dispatch(d: OnshapeDriver, tool: str | None, args: dict[str, Any]) -> None:
    """Route a tool call. Unknown tools raise — the LLM shouldn't call
    things not in the datasheet.
    """
    if not tool:
        return
    fn = TOOL_DISPATCH.get(tool)
    if fn is None:
        raise KeyError(f"unknown tool: {tool}")
    return await fn(d, args or {})


def build_agent_system_prompt() -> str:
    """The system prompt for the closed-loop agent. This is where I
    teach the model the workflow that actually works.
    """
    from . import tools as datasheet

    return (
        "You are an agent that drives the Onshape web CAD application visually, "
        "the way a human would. You see screenshots and call tools.\n\n"
        "On each turn:\n"
        "  1. Read the user's goal.\n"
        "  2. Look at the current screenshot.\n"
        "  3. Decide the single next tool to call. Pick ONE tool. Provide its "
        "arguments as a JSON object matching its signature.\n"
        "  4. If you have completed the goal, return {\"done\": true, \"summary\": \"...\"}.\n\n"
        "Coordinate space is viewport pixels (0,0 = top-left). Use viewport_size "
        "to get the bounds. The viewport center is typically the world origin in "
        "the default top view.\n\n"
        "## The constrained-sketch workflow (this is how you size things)\n\n"
        "Never try to pick exact-mm coordinates in the viewport. You don't know "
        "the px-to-mm ratio, and Onshape's zoom changes constantly. Instead:\n\n"
        "  1. sketch.start (clicks the top plane, lands at origin)\n"
        "  2. sketch.rectangle with any two sensible corners (e.g. near the center)\n"
        "  3. sketch.dimension twice — once for width, once for height — to set "
        "exact mm values. Onshape's solver does the geometry for you.\n"
        "  4. sketch.exit\n"
        "  5. feature.extrude with the depth in mm\n\n"
        "For a '5x5 square extruded 5mm into a cube' that's exactly 6 tool calls "
        "and works at any zoom level. The exact rectangle corner coordinates "
        "don't matter; the dimensions do.\n\n"
        "## Be conservative\n\n"
        "When in doubt, take a screenshot and re-look. The UI is fragile: wrong "
        "clicks can deselect, dismiss dialogs, or trigger unrelated tools. If a "
        "tool fails twice in a row, undo and try a different approach.\n\n"
        "## Available tools\n\n"
        + datasheet.as_prompt_block()
    )
