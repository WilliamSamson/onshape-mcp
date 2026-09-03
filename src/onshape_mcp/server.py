"""MCP server. Exposes the Onshape tool vocabulary as MCP tools. UI ops
live in ui_actions.py and use the driver.py primitives. Every call goes
through the journal so undo/replay/debug work.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import ui_actions
from .config import settings
from .dispatch import TOOL_DISPATCH, build_agent_system_prompt
from .driver import OnshapeDriver
from .journal import JournalEntry, journal
from .loop import AgentLoop
from .vision import GeminiWeb

mcp = FastMCP("onshape-mcp")

_driver: OnshapeDriver | None = None
_vision: GeminiWeb | None = None
_loop: AgentLoop | None = None


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


# ─── meta tools ───────────────────────────────────────────────────────────

@mcp.tool()
async def screenshot(name: str = "shot.png") -> str:
    """Take a screenshot of the current Onshape viewport. Returns the file path."""
    d = await _driver_lazy()
    path = await d.screenshot(name=name)
    e = JournalEntry.new("screenshot", {"name": name})
    e.screenshot = str(path)
    journal.append(e)
    return str(path)


@mcp.tool()
async def describe_view(question: str = "What do you see in the Onshape viewport?") -> str:
    """Screenshot + ask Gemini web to describe it. Returns the model's answer."""
    d = await _driver_lazy()
    img = await d.screenshot("describe.png")
    v = await _vision_lazy()
    return await v.ask_with_image(question, img)


@mcp.tool()
async def tool_datasheet() -> str:
    """Return the Onshape tool vocabulary as a markdown block."""
    return datasheet.as_prompt_block()


@mcp.tool()
async def journal_tail(n: int = 20) -> str:
    """Return the last N actions from the local journal (no screenshots)."""
    return json.dumps(journal.tail(n), indent=2, ensure_ascii=False)


@mcp.tool()
async def open_doc(url: str) -> str:
    """Navigate to an Onshape document URL or `d/<docId>/e/<elementId>` path."""
    d = await _driver_lazy()
    full = url if url.startswith("http") else f"https://cad.onshape.com/{url.lstrip('/')}"
    await d.open(full)
    journal.append(JournalEntry.new("doc.open", {"url": full}))
    return f"opened {full}"


@mcp.tool()
async def viewport_size() -> str:
    """Return the current viewport dimensions in pixels."""
    d = await _driver_lazy()
    return json.dumps(await d.viewport_box())


# ─── view / camera ────────────────────────────────────────────────────────

@mcp.tool()
async def onshape_view_fit() -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.view_fit(d)).to_dict())


@mcp.tool()
async def onshape_view_top() -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.view_top(d)).to_dict())


# ─── sketch ───────────────────────────────────────────────────────────────

@mcp.tool()
async def onshape_sketch_start(plane_x: float | None = None, plane_y: float | None = None) -> str:
    """Click the Sketch button, then click a plane. If no coords given, picks
    the center of the viewport (the default top plane)."""
    d = await _driver_lazy()
    plane = (plane_x, plane_y) if plane_x is not None and plane_y is not None else None
    return json.dumps((await ui_actions.sketch_start(d, plane)).to_dict())


@mcp.tool()
async def onshape_sketch_rectangle(
    corner1_x: float, corner1_y: float, corner2_x: float, corner2_y: float
) -> str:
    d = await _driver_lazy()
    return json.dumps(
        (await ui_actions.sketch_rectangle(
            d, (corner1_x, corner1_y), (corner2_x, corner2_y)
        )).to_dict()
    )


@mcp.tool()
async def onshape_sketch_circle(center_x: float, center_y: float, radius_px: float) -> str:
    d = await _driver_lazy()
    return json.dumps(
        (await ui_actions.sketch_circle(d, (center_x, center_y), radius_px)).to_dict()
    )


@mcp.tool()
async def onshape_sketch_line(p1_x: float, p1_y: float, p2_x: float, p2_y: float) -> str:
    d = await _driver_lazy()
    return json.dumps(
        (await ui_actions.sketch_line(d, (p1_x, p1_y), (p2_x, p2_y))).to_dict()
    )


@mcp.tool()
async def onshape_sketch_dimension(
    entity_x: float, entity_y: float, label_x: float, label_y: float, value_mm: float
) -> str:
    """Dimension an entity to an exact mm value. Click the entity, place the
    label, type the value, Enter. Use this in the constrained-sketch workflow
    to set exact sizes on a rectangle you drew at any size."""
    d = await _driver_lazy()
    return json.dumps(
        (await ui_actions.sketch_dimension(
            d, (entity_x, entity_y), (label_x, label_y), value_mm
        )).to_dict()
    )


@mcp.tool()
async def onshape_sketch_equal(x0: float, y0: float, x1: float, y1: float) -> str:
    """Equal constraint between two entities. Click two edges/sides to make
    them the same size. Useful for 'make this a square'."""
    d = await _driver_lazy()
    return json.dumps(
        (await ui_actions.sketch_equal(d, (x0, y0), (x1, y1))).to_dict()
    )


@mcp.tool()
async def onshape_sketch_exit() -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.sketch_exit(d)).to_dict())


# ─── features ─────────────────────────────────────────────────────────────

@mcp.tool()
async def onshape_feature_extrude(depth_mm: float | None = None) -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.feature_extrude(d, depth_mm)).to_dict())


@mcp.tool()
async def onshape_feature_fillet(radius_mm: float | None = None) -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.feature_fillet(d, radius_mm)).to_dict())


@mcp.tool()
async def onshape_feature_chamfer(distance_mm: float | None = None) -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.feature_chamfer(d, distance_mm)).to_dict())


# ─── selection ────────────────────────────────────────────────────────────

@mcp.tool()
async def onshape_select_face(x: float, y: float) -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.select_face(d, x, y)).to_dict())


@mcp.tool()
async def onshape_select_edge(x: float, y: float) -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.select_edge(d, x, y)).to_dict())


# ─── undo/redo ────────────────────────────────────────────────────────────

@mcp.tool()
async def onshape_ui_undo() -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.undo(d)).to_dict())


@mcp.tool()
async def onshape_ui_redo() -> str:
    d = await _driver_lazy()
    return json.dumps((await ui_actions.redo(d)).to_dict())


# ─── closed-loop agent ────────────────────────────────────────────────────

# Cap the loop so a runaway agent doesn't burn the day.
MAX_AGENT_STEPS = 25


@mcp.tool()
async def act(goal: str, max_steps: int = MAX_AGENT_STEPS) -> str:
    """Closed-loop agent: take a goal in natural language, drive the Onshape
    UI to achieve it. Uses Gemini web for vision + reasoning. Returns a
    summary of actions taken and the final screenshot.
    """
    loop = await _loop_lazy()
    result = await loop.run(goal, max_steps=max_steps)
    tail = [
        {
            "step": r.step,
            "tool": r.decision.get("tool"),
            "args": r.decision.get("args", {}),
            "ok": r.ok,
            "error": r.error,
        }
        for r in result.steps[-5:]
    ]
    return json.dumps(
        {
            "goal": goal,
            "completed": result.completed,
            "summary": result.summary(),
            "stop_reason": result.stop_reason,
            "steps_total": len(result.steps),
            "transcript_tail": tail,
            "final_screenshot": str(result.final_screenshot) if result.final_screenshot else None,
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
async def agent_system_prompt() -> str:
    """Return the system prompt used by the act() tool. Useful for debugging
    what the LLM sees."""
    return build_agent_system_prompt()


# ─── lifecycle ────────────────────────────────────────────────────────────

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
    try:
        mcp.run()
    finally:
        asyncio.run(_cleanup())


if __name__ == "__main__":
    main()
