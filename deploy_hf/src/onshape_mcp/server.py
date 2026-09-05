"""MCP server. Exposes the complete Onshape tool vocabulary as MCP tools.
Designed for Claude Desktop, ChatGPT, and custom LLM clients.

All tool executions are wrapped with error-handling to prevent JSON-RPC
pipe crashes and provide clear, human-readable public messages.
"""

from __future__ import annotations

import asyncio
import json
import re
import traceback
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import tools as datasheet
from . import ui_actions
from .dispatch import TOOL_DISPATCH, build_agent_system_prompt, dispatch
from .driver import OnshapeDriver
from .fast_exec import execute as fast_execute
from .intent import parse as parse_intent
from .journal import JournalEntry, journal
from .loop import AgentLoop
from .vision import GeminiWeb

mcp = FastMCP(
    "onshape-mcp",
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

_driver: OnshapeDriver | None = None
_vision: GeminiWeb | None = None
_loop: AgentLoop | None = None


def _format_error(tool_name: str, err: Exception) -> str:
    """Return a clean JSON string with public error details."""
    return json.dumps(
        {
            "ok": False,
            "tool": tool_name,
            "error": type(err).__name__,
            "message": str(err),
            "hint": "Check coordinates, tool preconditions, or document connection.",
        },
        indent=2,
    )


async def _driver_lazy() -> OnshapeDriver:
    global _driver
    if _driver is None:
        _driver = OnshapeDriver()
        await _driver.start(headless=True)
        await _driver.open()
    return _driver


async def _vision_lazy() -> GeminiWeb:
    global _vision
    if _vision is None:
        _vision = GeminiWeb()
    return _vision


async def _loop_lazy() -> AgentLoop:
    global _loop
    if _loop is None:
        _loop = AgentLoop()
    return _loop


# Meta & Information Tools


@mcp.tool()
async def screenshot(name: str = "shot.png") -> str:
    """Take a screenshot of the current Onshape viewport. Returns the absolute file path."""
    try:
        d = await _driver_lazy()
        path = await d.screenshot(name=name)
        e = JournalEntry.new("screenshot", {"name": name})
        e.screenshot = str(path)
        journal.append(e)
        return json.dumps({"ok": True, "screenshot": str(path), "message": f"Saved screenshot to {path}"})
    except Exception as e:
        return _format_error("screenshot", e)


@mcp.tool()
async def describe_view(question: str = "What do you see in the Onshape viewport?") -> str:
    """Screenshot + ask Gemini vision to describe what's in the viewport."""
    try:
        d = await _driver_lazy()
        img = await d.screenshot("describe.png")
        v = await _vision_lazy()
        desc = await v.ask_with_image(question, img)
        return json.dumps({"ok": True, "description": desc})
    except Exception as e:
        return _format_error("describe_view", e)


@mcp.tool()
async def tool_datasheet() -> str:
    """Return the entire Onshape tool vocabulary, parameters, and preconditions as markdown."""
    return datasheet.as_prompt_block()


@mcp.tool()
async def journal_tail(n: int = 20) -> str:
    """Return the last N actions executed against Onshape."""
    return json.dumps(journal.tail(n), indent=2, ensure_ascii=False)


@mcp.tool()
async def open_doc(url: str) -> str:
    """Navigate to an Onshape document URL or path."""
    try:
        d = await _driver_lazy()
        full = url if url.startswith("http") else f"https://cad.onshape.com/{url.lstrip('/')}"
        await d.open(full)
        journal.append(JournalEntry.new("doc.open", {"url": full}))
        return json.dumps({"ok": True, "message": f"Opened document {full}"})
    except Exception as e:
        return _format_error("open_doc", e)


@mcp.tool()
async def open_document(url: str) -> str:
    """Navigate to an Onshape document URL or path (alias for open_doc)."""
    return await open_doc(url=url)


@mcp.tool()
async def viewport_size() -> str:
    """Return the current viewport dimensions in pixels."""
    try:
        d = await _driver_lazy()
        return json.dumps(await d.viewport_box())
    except Exception as e:
        return _format_error("viewport_size", e)


# View & Camera Tools


@mcp.tool()
async def onshape_view_fit() -> str:
    """Zoom and pan to fit all visible geometry in the viewport ('f')."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.view_fit(d)).to_dict())
    except Exception as e:
        return _format_error("view.fit", e)


@mcp.tool()
async def onshape_view_top() -> str:
    """Orient camera to look directly at the Top view."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.view_top(d)).to_dict())
    except Exception as e:
        return _format_error("view.top", e)


@mcp.tool()
async def onshape_view_front() -> str:
    """Orient camera to look directly at the Front view."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.view_front(d)).to_dict())
    except Exception as e:
        return _format_error("view.front", e)


@mcp.tool()
async def onshape_view_iso() -> str:
    """Orient camera to Isometric view."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.view_iso(d)).to_dict())
    except Exception as e:
        return _format_error("view.iso", e)


# Sketch Creation Tools


@mcp.tool()
async def onshape_sketch_start(
    plane_x: float | None = None,
    plane_y: float | None = None,
    plane: str | None = None,
) -> str:
    """Open a new sketch. Pass plane name ('Top', 'Front', 'Right') or plane_x/plane_y coordinates.
    Default plane is 'Top'. Automatically aligns camera normal to the sketch plane."""
    try:
        d = await _driver_lazy()
        pt = (plane_x, plane_y) if plane_x is not None and plane_y is not None else None
        return json.dumps((await ui_actions.sketch_start(d, pt, plane_name=plane)).to_dict())
    except Exception as e:
        return _format_error("sketch.start", e)


@mcp.tool()
async def onshape_sketch_exit(commit: bool = True) -> str:
    """Exit the active sketch and accept (commit=True) or discard (commit=False) changes."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.sketch_exit(d, commit=commit)).to_dict())
    except Exception as e:
        return _format_error("sketch.exit", e)


@mcp.tool()
async def onshape_sketch_rectangle(
    corner1_x: float | None = None,
    corner1_y: float | None = None,
    corner2_x: float | None = None,
    corner2_y: float | None = None,
    width: float | str | None = None,
    height: float | str | None = None,
    quadrant: str | int | None = None,
    centered: bool | None = None,
) -> str:
    """Draw a rectangle. Accepts dimensions (e.g. width='10 cm', height='5 cm'), quadrant ('1', '2', '3', '4'),
    or centered=True. Dimensions are automatically driven into Onshape's solver."""
    try:
        d = await _driver_lazy()
        c1 = (corner1_x, corner1_y) if corner1_x is not None and corner1_y is not None else None
        c2 = (corner2_x, corner2_y) if corner2_x is not None and corner2_y is not None else None
        return json.dumps(
            (
                await ui_actions.sketch_rectangle(
                    d, c1, c2, width=width, height=height, quadrant=quadrant, centered=centered
                )
            ).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.rectangle", e)


@mcp.tool()
async def onshape_sketch_circle(
    center_x: float | None = None,
    center_y: float | None = None,
    radius_px: float = 50.0,
    centered: bool | None = None,
) -> str:
    """Draw a circle. Pass center coordinates (center_x, center_y) or centered=True for origin."""
    try:
        d = await _driver_lazy()
        center = (center_x, center_y) if center_x is not None and center_y is not None else None
        return json.dumps(
            (await ui_actions.sketch_circle(d, center, radius_px, centered=centered)).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.circle", e)


@mcp.tool()
async def onshape_sketch_line(p1_x: float, p1_y: float, p2_x: float, p2_y: float) -> str:
    """Draw a line segment from (p1_x, p1_y) to (p2_x, p2_y)."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.sketch_line(d, (p1_x, p1_y), (p2_x, p2_y))).to_dict())
    except Exception as e:
        return _format_error("sketch.line", e)


@mcp.tool()
async def onshape_sketch_polygon(
    sides: int = 6,
    radius: float = 60.0,
    center_x: float | None = None,
    center_y: float | None = None,
    circumscribed: bool = False,
) -> str:
    """Draw an inscribed or circumscribed polygon with N sides and radius."""
    try:
        d = await _driver_lazy()
        center = (center_x, center_y) if center_x is not None and center_y is not None else None
        return json.dumps(
            (
                await ui_actions.sketch_polygon(
                    d, center=center, radius=radius, sides=sides, circumscribed=circumscribed
                )
            ).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.polygon", e)


@mcp.tool()
async def onshape_sketch_spline(points: list[list[float]]) -> str:
    """Draw a smooth spline curve through a list of [[x1, y1], [x2, y2], ...] points."""
    try:
        d = await _driver_lazy()
        pts = [(p[0], p[1]) for p in points]
        return json.dumps((await ui_actions.sketch_spline(d, pts)).to_dict())
    except Exception as e:
        return _format_error("sketch.spline", e)


@mcp.tool()
async def onshape_sketch_arc(
    p1_x: float,
    p1_y: float,
    p2_x: float,
    p2_y: float,
    radius_x: float | None = None,
    radius_y: float | None = None,
) -> str:
    """Draw a 3-point arc from (p1_x, p1_y) to (p2_x, p2_y) passing through (radius_x, radius_y)."""
    try:
        d = await _driver_lazy()
        rad_pt = (radius_x, radius_y) if radius_x is not None and radius_y is not None else None
        return json.dumps(
            (await ui_actions.sketch_arc(d, (p1_x, p1_y), (p2_x, p2_y), radius_pt=rad_pt)).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.arc", e)


@mcp.tool()
async def onshape_sketch_point(x: float, y: float) -> str:
    """Place a sketch point at (x, y)."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.sketch_point(d, (x, y))).to_dict())
    except Exception as e:
        return _format_error("sketch.point", e)


@mcp.tool()
async def onshape_sketch_text(
    corner1_x: float, corner1_y: float, corner2_x: float, corner2_y: float, text: str
) -> str:
    """Place sketch text in a box defined by corner1 and corner2."""
    try:
        d = await _driver_lazy()
        return json.dumps(
            (
                await ui_actions.sketch_text(
                    d, (corner1_x, corner1_y), (corner2_x, corner2_y), text=text
                )
            ).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.text", e)


# Sketch Modifications & Operations


@mcp.tool()
async def onshape_sketch_construction(x: float | None = None, y: float | None = None) -> str:
    """Toggle construction mode, or convert the entity at (x, y) to/from construction geometry ('q')."""
    try:
        d = await _driver_lazy()
        pt = (x, y) if x is not None and y is not None else None
        return json.dumps((await ui_actions.sketch_construction(d, pt=pt)).to_dict())
    except Exception as e:
        return _format_error("sketch.construction", e)


@mcp.tool()
async def onshape_sketch_fillet(vertex_x: float, vertex_y: float, radius_mm: float = 5.0) -> str:
    """Add a rounded 2D fillet of radius_mm at corner/vertex (vertex_x, vertex_y)."""
    try:
        d = await _driver_lazy()
        return json.dumps(
            (await ui_actions.sketch_fillet(d, (vertex_x, vertex_y), radius_mm=radius_mm)).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.fillet", e)


@mcp.tool()
async def onshape_sketch_chamfer(
    vertex_x: float, vertex_y: float, distance_mm: float = 5.0
) -> str:
    """Add a 2D chamfer of distance_mm at corner/vertex (vertex_x, vertex_y)."""
    try:
        d = await _driver_lazy()
        return json.dumps(
            (
                await ui_actions.sketch_chamfer(d, (vertex_x, vertex_y), distance_mm=distance_mm)
            ).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.chamfer", e)


@mcp.tool()
async def onshape_sketch_trim(x: float, y: float) -> str:
    """Trim a curve segment back to the nearest intersections by clicking at (x, y) ('m')."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.sketch_trim(d, (x, y))).to_dict())
    except Exception as e:
        return _format_error("sketch.trim", e)


@mcp.tool()
async def onshape_sketch_extend(x: float, y: float) -> str:
    """Extend a curve endpoint at (x, y) to the nearest boundary ('x')."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.sketch_extend(d, (x, y))).to_dict())
    except Exception as e:
        return _format_error("sketch.extend", e)


@mcp.tool()
async def onshape_sketch_offset(
    entity_x: float,
    entity_y: float,
    distance_mm: float = 5.0,
    side_x: float | None = None,
    side_y: float | None = None,
) -> str:
    """Offset curve at (entity_x, entity_y) by distance_mm toward optional side (side_x, side_y) ('o')."""
    try:
        d = await _driver_lazy()
        side = (side_x, side_y) if side_x is not None and side_y is not None else None
        return json.dumps(
            (
                await ui_actions.sketch_offset(
                    d, (entity_x, entity_y), distance_mm=distance_mm, side_xy=side
                )
            ).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.offset", e)


@mcp.tool()
async def onshape_sketch_mirror(
    centerline_x: float, centerline_y: float, entity_x: float, entity_y: float
) -> str:
    """Mirror an entity at (entity_x, entity_y) across a centerline at (centerline_x, centerline_y)."""
    try:
        d = await _driver_lazy()
        return json.dumps(
            (
                await ui_actions.sketch_mirror(
                    d, (centerline_x, centerline_y), (entity_x, entity_y)
                )
            ).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.mirror", e)


# Dimensions & Constraints


@mcp.tool()
async def onshape_sketch_dimension(
    entity_x: float, entity_y: float, label_x: float, label_y: float, value_mm: float | str
) -> str:
    """Drive an Onshape sketch dimension ('d'). Clicks entity at (entity_x, entity_y), places label
    at (label_x, label_y), and enters value_mm into the solver."""
    try:
        d = await _driver_lazy()
        return json.dumps(
            (
                await ui_actions.sketch_dimension(
                    d, (entity_x, entity_y), (label_x, label_y), value_mm
                )
            ).to_dict()
        )
    except Exception as e:
        return _format_error("sketch.dimension", e)


@mcp.tool()
async def onshape_sketch_constrain(
    constraint_type: str,
    entities: list[list[float]],
) -> str:
    """Apply a geometric constraint across entities.
    Valid types: coincident, concentric, parallel, tangent, horizontal, vertical,
    perpendicular, equal, midpoint, normal, pierce, symmetric, fix."""
    try:
        d = await _driver_lazy()
        pts = [(e[0], e[1]) for e in entities]
        return json.dumps(
            (await ui_actions.sketch_constrain(d, constraint_type, *pts)).to_dict()
        )
    except Exception as e:
        return _format_error(f"constraint.{constraint_type}", e)


# Feature Operations


@mcp.tool()
async def onshape_feature_extrude(depth_mm: float | None = None) -> str:
    """Extrude the active sketch or selected face by depth_mm."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.feature_extrude(d, depth_mm)).to_dict())
    except Exception as e:
        return _format_error("feature.extrude", e)


@mcp.tool()
async def onshape_feature_fillet(radius_mm: float | None = None) -> str:
    """Round selected 3D model edges by radius_mm."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.feature_fillet(d, radius_mm)).to_dict())
    except Exception as e:
        return _format_error("feature.fillet", e)


@mcp.tool()
async def onshape_feature_chamfer(distance_mm: float | None = None) -> str:
    """Bevel selected 3D model edges by distance_mm."""
    try:
        d = await _driver_lazy()
        return json.dumps((await ui_actions.feature_chamfer(d, distance_mm)).to_dict())
    except Exception as e:
        return _format_error("feature.chamfer", e)


# Generic Tool Dispatcher (with clean un-bound tool guard)


@mcp.tool()
async def onshape_execute(tool: str, args: dict[str, Any] | None = None) -> str:
    """Generic tool dispatcher. Calls any registered tool by name with arguments.
    Returns clear public error messages if a tool is un-bound or fails."""
    if tool not in TOOL_DISPATCH:
        return json.dumps(
            {
                "ok": False,
                "tool": tool,
                "error": "ToolNotBoundError",
                "message": f"Tool '{tool}' is not bound or supported. Please choose from available tools.",
                "available_tools": sorted(TOOL_DISPATCH.keys()),
            },
            indent=2,
        )
    try:
        d = await _driver_lazy()
        res = await dispatch(d, tool, args or {})
        out = res.to_dict() if hasattr(res, "to_dict") else {"ok": True, "result": str(res)}
        return json.dumps(out, indent=2)
    except Exception as e:
        return _format_error(tool, e)


# Autonomous Agent (Fast Path + Vision Loop)


@mcp.tool()
async def act(goal: str, max_steps: int = 25) -> str:
    """Autonomous CAD agent. Takes a high-level goal in natural language (e.g.
    'draw a 10cm by 5cm box in Quadrant 1 on the top plane', 'draw a 6-sided polygon')
    and executes it. Tries deterministic fast execution first (10-20s), falling back
    to vision loop if ambiguous."""
    try:
        d: OnshapeDriver | None = None
        url_match = re.search(r"https://cad\.onshape\.com/[^\s)\]]+", goal)
        if url_match:
            d = await _driver_lazy()
            await d.open(url_match.group(0))

        lower_goal = goal.lower()
        if any(word in lower_goal for word in ("list", "show", "existing")) and any(
            word in lower_goal for word in ("feature", "features", "sketch", "sketches")
        ):
            d = d or await _driver_lazy()
            listed = await ui_actions.features_list(d)
            return json.dumps(
                {
                    "ok": listed.ok,
                    "mode": "deterministic_inspection",
                    "features": listed.meta.get("features", []),
                    "summary": listed.note,
                },
                indent=2,
            )

        # 1. Try fast path first
        plan = parse_intent(goal)
        if plan is not None:
            d = d or await _driver_lazy()
            result_fast = await fast_execute(d, plan)
            return json.dumps(
                {
                    "ok": result_fast.ok,
                    "mode": "fast_path",
                    "goal": goal,
                    "summary": result_fast.summary(),
                    "actions_count": len(result_fast.step_times),
                    "total_elapsed_s": round(result_fast.total_elapsed_s, 1),
                    "final_screenshot": str(result_fast.final_screenshot)
                    if result_fast.final_screenshot
                    else None,
                    "error": result_fast.error,
                },
                indent=2,
            )

        # 2. Fallback to vision loop
        loop = await _loop_lazy()
        result_loop = await loop.run(goal, max_steps=max_steps)
        tail = [
            {
                "step": r.step,
                "tool": r.decision.get("tool"),
                "args": r.decision.get("args", {}),
                "ok": r.ok,
                "error": r.error,
            }
            for r in result_loop.steps[-5:]
        ]
        return json.dumps(
            {
                "ok": result_loop.completed,
                "mode": "vision_loop",
                "goal": goal,
                "summary": result_loop.summary(),
                "total_elapsed_s": round(result_loop.total_elapsed_s, 1),
                "steps_total": len(result_loop.steps),
                "transcript_tail": tail,
                "final_screenshot": str(result_loop.final_screenshot)
                if result_loop.final_screenshot
                else None,
                "stop_reason": result_loop.stop_reason,
            },
            indent=2,
        )
    except Exception as e:
        return _format_error("act", e)


# Feature Tree & History Management


@mcp.tool()
async def onshape_feature_delete(name: str) -> str:
    """Delete a feature or sketch by name (e.g. 'Sketch 1', 'Sketch 2', 'Extrude 1') from the Part Studio tree."""
    try:
        d = await _driver_lazy()
        res = await ui_actions.feature_delete(d, name)
        return json.dumps({"ok": res.ok, "message": res.note, "screenshot": str(res.screenshot) if res.screenshot else None})
    except Exception as e:
        return _format_error("onshape_feature_delete", e)


@mcp.tool()
async def onshape_delete(name: str) -> str:
    """Delete a feature or sketch by name (alias for onshape_feature_delete)."""
    return await onshape_feature_delete(name)


@mcp.tool()
async def onshape_feature_edit(name: str) -> str:
    """Open an existing feature or sketch (e.g. 'Sketch 1') for editing."""
    try:
        d = await _driver_lazy()
        res = await ui_actions.feature_edit(d, name)
        return json.dumps({"ok": res.ok, "message": res.note, "screenshot": str(res.screenshot) if res.screenshot else None})
    except Exception as e:
        return _format_error("onshape_feature_edit", e)


@mcp.tool()
async def onshape_features_list() -> str:
    """List all features currently in the Part Studio tree."""
    try:
        d = await _driver_lazy()
        res = await ui_actions.features_list(d)
        return json.dumps({"ok": res.ok, "features": res.meta.get("features", []), "message": res.note})
    except Exception as e:
        return _format_error("onshape_features_list", e)


@mcp.tool()
async def onshape_undo() -> str:
    """Undo the last action in Onshape."""
    try:
        d = await _driver_lazy()
        res = await ui_actions.doc_undo(d)
        return json.dumps({"ok": res.ok, "message": res.note})
    except Exception as e:
        return _format_error("onshape_undo", e)


@mcp.tool()
async def onshape_redo() -> str:
    """Redo the last undone action in Onshape."""
    try:
        d = await _driver_lazy()
        res = await ui_actions.doc_redo(d)
        return json.dumps({"ok": res.ok, "message": res.note})
    except Exception as e:
        return _format_error("onshape_redo", e)


# Lifecycle


async def _cleanup() -> None:
    global _driver, _vision, _loop
    if _loop is not None:
        await _loop.close()
    if _vision is not None:
        await _vision.close()
    if _driver is not None:
        await _driver.close()
    _driver = None
    _vision = None
    _loop = None


def main() -> None:
    import argparse
    import os
    import sys

    # Quick dispatch for setup wizard or login
    if len(sys.argv) >= 2 and sys.argv[1] == "setup":
        from .setup import main as run_setup

        sys.argv.pop(1)
        run_setup()
        return

    if len(sys.argv) >= 2 and sys.argv[1] == "login":
        from .driver import login_interactive

        asyncio.run(login_interactive())
        return

    if len(sys.argv) >= 2 and sys.argv[1] in ("share", "tunnel"):
        from .tunnel import run_tunnel_and_server

        port = int(os.environ.get("PORT", os.environ.get("MCP_PORT", "8000")))
        run_tunnel_and_server(port=port)
        return

    parser = argparse.ArgumentParser(description="Onshape MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=os.environ.get("MCP_TRANSPORT", "stdio"),
        help="Transport protocol: 'stdio' for Claude Desktop / LLM clients (default), or 'sse' for remote hosting.",
    )
    parser.add_argument(
        "--tunnel",
        action="store_true",
        help="Auto-start Cloudflare tunnel to expose live HTTPS link for ChatGPT Web / LibreChat.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Host interface for SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", os.environ.get("MCP_PORT", "8000"))),
        help="Port for SSE transport (default: 8000 or $PORT)",
    )
    args, _ = parser.parse_known_args()

    if args.tunnel:
        from .tunnel import run_tunnel_and_server

        run_tunnel_and_server(port=args.port, host=args.host)
        return

    if args.transport == "sse":
        mcp.settings.host = args.host
        mcp.settings.port = args.port

    try:
        mcp.run(transport=args.transport)
    finally:
        asyncio.run(_cleanup())


if __name__ == "__main__":
    main()
