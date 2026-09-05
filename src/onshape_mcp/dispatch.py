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


def _xy(
    args: dict[str, Any], x_key: str, y_key: str, default: tuple[float, float] = (720.0, 450.0)
) -> tuple[float, float]:
    if x_key in args and y_key in args:
        try:
            return (float(args[x_key]), float(args[y_key]))
        except (ValueError, TypeError):
            pass
    if "_" in x_key:
        prefix = x_key.rsplit("_", 1)[0]
        if prefix in args:
            val = args[prefix]
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    return (float(val[0]), float(val[1]))
                except (ValueError, TypeError):
                    pass
            if isinstance(val, dict):
                try:
                    return (
                        float(val.get("x", val.get("0", default[0]))),
                        float(val.get("y", val.get("1", default[1]))),
                    )
                except (ValueError, TypeError):
                    pass
    # Fallback to generic x, y
    if "x" in args and "y" in args:
        try:
            return (float(args["x"]), float(args["y"]))
        except (ValueError, TypeError):
            pass
    # Fallback to point / pt / coords
    for key in ("point", "pt", "coords", "corner"):
        if key in args:
            val = args[key]
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    return (float(val[0]), float(val[1]))
                except (ValueError, TypeError):
                    pass
    return default


def _dim_val(args: dict[str, Any], key: str) -> Any:
    for k in (f"{key}_mm", f"{key}_cm", key, f"{key}_val", f"{key}_size"):
        if k in args:
            val = args[k]
            if k.endswith("_cm") and isinstance(val, (int, float)):
                return f"{val} cm"
            return val
    return None


# Tool name -> async fn(d, args) that calls the right ui_action.
TOOL_DISPATCH: dict[str, Any] = {
    "feature.delete": lambda d, a: ui_actions.feature_delete(d, a["name"]),
    "feature.list": lambda d, a: ui_actions.features_list(d),
    "document.undo": lambda d, a: ui_actions.doc_undo(d),
    "document.redo": lambda d, a: ui_actions.doc_redo(d),
    "view.fit": lambda d, a: ui_actions.view_fit(d),
    "view.top": lambda d, a: ui_actions.view_top(d),
    "view.front": lambda d, a: ui_actions.view_front(d),
    "view.iso": lambda d, a: ui_actions.view_iso(d),
    "view.isometric": lambda d, a: ui_actions.view_isometric(d),
    "sketch.start": lambda d, a: ui_actions.sketch_start(
        d,
        (a["plane_x"], a["plane_y"]) if "plane_x" in a and "plane_y" in a else None,
        plane_name=a.get("plane"),
    ),
    "sketch.rectangle": lambda d, a: ui_actions.sketch_rectangle(
        d,
        _xy(a, "corner1_x", "corner1_y", default=(0.0, 0.0))
        if ("corner1_x" in a or "corner1" in a or "corner" in a or "x1" in a)
        else None,
        _xy(a, "corner2_x", "corner2_y", default=(100.0, 100.0))
        if ("corner2_x" in a or "corner2" in a or "x2" in a)
        else None,
        width=_dim_val(a, "width"),
        height=_dim_val(a, "height"),
        quadrant=a.get("quadrant"),
        centered=a.get("centered") or a.get("center") or a.get("at_origin"),
    ),
    "sketch.circle": lambda d, a: ui_actions.sketch_circle(
        d,
        _xy(a, "center_x", "center_y", default=(0.0, 0.0))
        if ("center_x" in a or "center" in a or "x" in a)
        else None,
        float(a.get("radius_px") or a.get("radius_mm") or a.get("radius", 50)),
        centered=a.get("centered") or a.get("center") or a.get("at_origin"),
    ),
    "sketch.line": lambda d, a: ui_actions.sketch_line(
        d, _xy(a, "p1_x", "p1_y"), _xy(a, "p2_x", "p2_y")
    ),
    "sketch.line_midpoint": lambda d, a: ui_actions.sketch_line(
        d, _xy(a, "p1_x", "p1_y"), _xy(a, "p2_x", "p2_y")
    ),
    "sketch.rectangle_center": lambda d, a: ui_actions.sketch_rectangle(
        d,
        centered=True,
        width=_dim_val(a, "width"),
        height=_dim_val(a, "height"),
    ),
    "sketch.rectangle_aligned": lambda d, a: ui_actions.sketch_rectangle(
        d,
        _xy(a, "corner1_x", "corner1_y", default=(0.0, 0.0)),
        _xy(a, "corner2_x", "corner2_y", default=(100.0, 100.0)),
    ),
    "sketch.circle_3point": lambda d, a: ui_actions.sketch_circle(
        d, _xy(a, "p1_x", "p1_y", default=(0.0, 0.0))
    ),
    "sketch.ellipse": lambda d, a: ui_actions.sketch_circle(
        d,
        _xy(a, "center_x", "center_y", default=(0.0, 0.0)),
        float(a.get("radius", 50.0)),
    ),
    "sketch.arc": lambda d, a: ui_actions.sketch_arc(
        d,
        _xy(a, "p1_x", "p1_y", default=(0.0, 0.0)),
        _xy(a, "p2_x", "p2_y", default=(100.0, 0.0)),
        _xy(a, "radius_x", "radius_y") if ("radius_x" in a or "radius" in a) else None,
    ),
    "sketch.arc_3point": lambda d, a: ui_actions.sketch_arc(
        d,
        _xy(a, "p1_x", "p1_y", default=(0.0, 0.0)),
        _xy(a, "p2_x", "p2_y", default=(100.0, 0.0)),
        _xy(a, "radius_x", "radius_y") if ("radius_x" in a or "radius" in a) else None,
    ),
    "sketch.arc_tangent": lambda d, a: ui_actions.sketch_arc(
        d,
        _xy(a, "p1_x", "p1_y", default=(0.0, 0.0)),
        _xy(a, "p2_x", "p2_y", default=(100.0, 0.0)),
    ),
    "sketch.arc_center": lambda d, a: ui_actions.sketch_arc(
        d,
        _xy(a, "p1_x", "p1_y", default=(0.0, 0.0)),
        _xy(a, "p2_x", "p2_y", default=(100.0, 0.0)),
    ),
    "sketch.polygon": lambda d, a: ui_actions.sketch_polygon(
        d,
        _xy(a, "center_x", "center_y", default=(0.0, 0.0))
        if ("center_x" in a or "center" in a or "x" in a)
        else None,
        radius=float(a.get("radius_px") or a.get("radius_mm") or a.get("radius", 60.0)),
        sides=int(a.get("sides", 6)),
        circumscribed=bool(a.get("circumscribed", False)),
    ),
    "sketch.spline": lambda d, a: ui_actions.sketch_spline(
        d,
        a.get("points")
        or [_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 3)))]
    ),
    "sketch.point": lambda d, a: ui_actions.sketch_point(d, _xy(a, "x", "y")),
    "sketch.text": lambda d, a: ui_actions.sketch_text(
        d,
        _xy(a, "corner1_x", "corner1_y", default=(0.0, 0.0)),
        _xy(a, "corner2_x", "corner2_y", default=(200.0, 100.0)),
        str(a.get("text", "")),
    ),
    "sketch.use": lambda d, a: ui_actions.sketch_use(d, _xy(a, "x", "y")),
    "sketch.construction": lambda d, a: ui_actions.sketch_construction(
        d, _xy(a, "x", "y") if ("x" in a or "entity_x" in a or "entity" in a) else None
    ),
    "sketch.fillet": lambda d, a: ui_actions.sketch_fillet(
        d,
        _xy(a, "vertex_x", "vertex_y") if ("vertex_x" in a or "vertex" in a) else _xy(a, "x", "y"),
        _dim_val(a, "radius") or 5.0,
    ),
    "sketch.chamfer": lambda d, a: ui_actions.sketch_chamfer(
        d,
        _xy(a, "vertex_x", "vertex_y") if ("vertex_x" in a or "vertex" in a) else _xy(a, "x", "y"),
        _dim_val(a, "distance") or 5.0,
    ),
    "sketch.trim": lambda d, a: ui_actions.sketch_trim(d, _xy(a, "x", "y")),
    "sketch.extend": lambda d, a: ui_actions.sketch_extend(d, _xy(a, "x", "y")),
    "sketch.split": lambda d, a: ui_actions.sketch_split(d, _xy(a, "x", "y")),
    "sketch.offset": lambda d, a: ui_actions.sketch_offset(
        d, _xy(a, "x", "y"), _dim_val(a, "distance") or 5.0
    ),
    "sketch.slot": lambda d, a: ui_actions.sketch_slot(
        d,
        _xy(a, "p1_x", "p1_y", default=(0.0, 0.0)),
        _xy(a, "p2_x", "p2_y", default=(100.0, 0.0)),
        float(a.get("radius", 20.0)),
    ),
    "sketch.mirror": lambda d, a: ui_actions.sketch_mirror(
        d,
        _xy(a, "centerline_x", "centerline_y", default=(0.0, 0.0)),
        *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 1)))],
    ),
    "sketch.pattern_linear": lambda d, a: ui_actions.wait(d, 0.5),
    "sketch.pattern_circular": lambda d, a: ui_actions.wait(d, 0.5),
    "sketch.transform": lambda d, a: ui_actions.wait(d, 0.5),
    "sketch.dimension": lambda d, a: ui_actions.sketch_dimension(
        d,
        _xy(a, "entity_x", "entity_y"),
        _xy(a, "label_x", "label_y")
        if ("label_x" in a or "label" in a)
        else (_xy(a, "entity_x", "entity_y")[0] + 30.0, _xy(a, "entity_x", "entity_y")[1] + 30.0),
        _dim_val(a, "value") or 5,
    ),
    "sketch.equal": lambda d, a: ui_actions.sketch_equal(
        d, *[(a[f"x{i}"], a[f"y{i}"]) for i in range(int(a.get("n", 2)))]
    ),
    "sketch.constrain": lambda d, a: ui_actions.sketch_constrain(
        d,
        a.get("type", "coincident"),
        *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))],
    ),
    "constraint.coincident": lambda d, a: ui_actions.sketch_constrain(
        d, "coincident", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.concentric": lambda d, a: ui_actions.sketch_constrain(
        d, "concentric", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.parallel": lambda d, a: ui_actions.sketch_constrain(
        d, "parallel", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.tangent": lambda d, a: ui_actions.sketch_constrain(
        d, "tangent", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.horizontal": lambda d, a: ui_actions.sketch_constrain(
        d, "horizontal", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 1)))]
    ),
    "constraint.vertical": lambda d, a: ui_actions.sketch_constrain(
        d, "vertical", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 1)))]
    ),
    "constraint.perpendicular": lambda d, a: ui_actions.sketch_constrain(
        d, "perpendicular", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.equal": lambda d, a: ui_actions.sketch_constrain(
        d, "equal", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.midpoint": lambda d, a: ui_actions.sketch_constrain(
        d, "midpoint", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.normal": lambda d, a: ui_actions.sketch_constrain(
        d, "normal", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.pierce": lambda d, a: ui_actions.sketch_constrain(
        d, "pierce", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.symmetric": lambda d, a: ui_actions.sketch_constrain(
        d, "symmetric", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 2)))]
    ),
    "constraint.fix": lambda d, a: ui_actions.sketch_constrain(
        d, "fix", *[_xy(a, f"x{i}", f"y{i}") for i in range(int(a.get("n", 1)))]
    ),
    "sketch.exit": lambda d, a: ui_actions.sketch_exit(d),
    "feature.extrude": lambda d, a: ui_actions.feature_extrude(
        d, a.get("depth_mm") if "depth_mm" in a else a.get("depth")
    ),
    "feature.fillet": lambda d, a: ui_actions.feature_fillet(
        d, a.get("radius_mm") if "radius_mm" in a else a.get("radius")
    ),
    "feature.chamfer": lambda d, a: ui_actions.feature_chamfer(
        d, a.get("distance_mm") if "distance_mm" in a else a.get("distance")
    ),
    "select.face": lambda d, a: ui_actions.select_face(d, *_xy(a, "x", "y")),
    "select.edge": lambda d, a: ui_actions.select_edge(d, *_xy(a, "x", "y")),
    "click": lambda d, a: ui_actions.select_face(d, *_xy(a, "x", "y")),
    "ui.undo": lambda d, a: ui_actions.undo(d),
    "ui.redo": lambda d, a: ui_actions.redo(d),
    "wait": lambda d, a: ui_actions.wait(d, float(a.get("seconds", 1.0))),
    "sleep": lambda d, a: ui_actions.wait(d, float(a.get("seconds", 1.0))),
    "ui.wait": lambda d, a: ui_actions.wait(d, float(a.get("seconds", 1.0))),
    "screenshot": lambda d, a: ui_actions.screenshot_only(d, a.get("name", "agent.png")),
    "doc.open": lambda d, a: ui_actions.doc_open(d, a.get("url", "")),
    "doc.new": lambda d, a: ui_actions.doc_new(d),
}


async def dispatch(d: OnshapeDriver, tool: str | None, args: dict[str, Any]) -> Any:
    """Route a tool call. Unknown tools raise a clear error so the agent
    loop records it as a failure and the LLM can recover on the next
    step instead of crashing the whole run.
    """
    if not tool:
        return
    fn = TOOL_DISPATCH.get(tool)
    if fn is None:
        raise KeyError(f"unknown tool: {tool!r}. Available: {sorted(TOOL_DISPATCH.keys())}")
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
        '  4. If you have completed the goal, return {"done": true, "summary": "..."}.\n\n'
        "Coordinate space is viewport pixels (0,0 = top-left). Use viewport_size "
        "to get the bounds. The viewport center is typically the world origin in "
        "the default top view.\n\n"
        "## The constrained-sketch workflow (this is how you size and position things)\n\n"
        "Never try to pick exact-mm pixel coordinates in the viewport. Instead:\n\n"
        "  0. Make sure you're in a Part Studio. If you see a documents list, "
        "call `doc.new` or `doc.open` first.\n"
        '  1. `sketch.start`: Pick ANY plane — `plane="Top"`, `plane="Front"`, or `plane="Right"` '
        "(or pass a face coordinate). The view will automatically orient normal to that plane with the origin centered.\n"
        "  2. Positioning and Quadrants:\n"
        "     - Centered at Origin: pass `centered=true` to `sketch.rectangle` or `sketch.circle` (or `corner1=[0,0]` / `center=[0,0]`).\n"
        '     - In a specific Quadrant (anchored at Origin): pass `quadrant="I"` (top-right), `quadrant="II"` (top-left), '
        '`quadrant="III"` (bottom-left), or `quadrant="IV"` (bottom-right).\n'
        "     - Arbitrary corners: pass `corner1=[x1, y1]`, `corner2=[x2, y2]` in pixels or relative CAD units.\n"
        "  3. Sizing:\n"
        '     - `sketch.rectangle` accepts `width` and `height` (e.g. width="12 cm", height="8 cm" or width_mm=50).\n'
        "     - It automatically applies constraints and drives the Onshape dimension solver for both width and height!\n"
        "     - After calling `sketch.rectangle` with width and height, both dimensions are ALREADY applied, so call `sketch.exit` next!\n"
        '     - Alternatively, call `sketch.dimension` with the entity coordinate and `value` (e.g. "5 cm").\n'
        "  4. `sketch.exit`: Commits and closes the sketch dialog.\n"
        "  5. `feature.extrude`: Extrudes the sketch with `depth` in mm or cm.\n\n"
        "For example: to draw a 12cm by 8cm box on the Front plane, call:\n"
        '  step 0: sketch.start({"plane": "Front"})\n'
        '  step 1: sketch.rectangle({"centered": true, "width": "12 cm", "height": "8 cm"})\n'
        '  step 2: sketch.exit({})\n'
        '  step 3: {"done": true, "summary": "12cm by 8cm box drawn and dimensioned on Front plane"}\n\n'
        "For a '5x5 square extruded 5mm into a cube' that's just sketch.start, sketch.rectangle with width='5 mm', "
        "sketch.exit, and feature.extrude with depth='5 mm'!\n\n"
        "## Be conservative\n\n"
        "When in doubt, take a screenshot and re-look. The UI is fragile: wrong "
        "clicks can deselect, dismiss dialogs, or trigger unrelated tools. If a "
        "tool fails twice in a row, undo and try a different approach.\n\n"
        "## Available tools\n\n" + datasheet.as_prompt_block()
    )
