"""MCP server. Exposes the Onshape tool vocabulary as MCP tools. UI ops
live in ui_actions.py and use the driver.py primitives. Every call goes
through the journal so undo/replay/debug work.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools as datasheet
from . import ui_actions
from .config import settings
from .driver import OnshapeDriver
from .journal import JournalEntry, journal
from .vision import GeminiWeb

mcp = FastMCP("onshape-mcp")

_driver: OnshapeDriver | None = None
_vision: GeminiWeb | None = None


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
STUCK_THRESHOLD = 3  # if 3 actions in a row don't change the screenshot, stop


def _build_agent_system_prompt() -> str:
    return (
        "You are an agent that drives the Onshape web CAD application visually, "
        "the way a human would. You see screenshots and call tools.\n\n"
        "On each turn:\n"
        "  1. Read the user's goal.\n"
        "  2. Look at the current screenshot.\n"
        "  3. Decide the single next tool to call. Pick ONE tool. Provide its "
        "arguments as a JSON object matching its signature.\n"
        "  4. If you have completed the goal, return {\"done\": true, \"summary\": \"...\"}.\n\n"
        "Be conservative. When in doubt, take a screenshot and re-look. The UI "
        "is fragile: wrong clicks can deselect, dismiss dialogs, or trigger "
        "unrelated tools.\n\n"
        "Coordinate space: viewport pixels (0,0 = top-left). Use the "
        "`viewport_size` tool if you need the bounds.\n\n"
        "Available tools:\n\n"
        + datasheet.as_prompt_block()
    )


@mcp.tool()
async def act(goal: str, max_steps: int = MAX_AGENT_STEPS) -> str:
    """Closed-loop agent: take a goal in natural language, drive the Onshape
    UI to achieve it. Uses Gemini web for vision + reasoning. Returns a
    summary of actions taken and the final screenshot.
    """
    d = await _driver_lazy()
    v = await _vision_lazy()

    transcript: list[dict[str, Any]] = []
    last_shot_hash: str | None = None
    unchanged = 0

    for step in range(max_steps):
        shot = await d.screenshot(f"act_step_{step:02d}.png")
        # Cheap stickiness check: file size + first bytes. Not cryptographic.
        h = shot.read_bytes()[:4096].hex()
        if h == last_shot_hash:
            unchanged += 1
            if unchanged >= STUCK_THRESHOLD:
                transcript.append({"step": step, "stopped": "stuck", "reason": "no UI change"})
                break
        else:
            unchanged = 0
        last_shot_hash = h

        prompt = (
            f"User goal: {goal}\n\n"
            f"Step {step + 1}/{max_steps}.\n"
            "Look at the screenshot. Reply with JSON: "
            '{"tool": "<tool_name>", "args": {...}} OR {"done": true, "summary": "..."}'
        )
        try:
            answer = await v.ask_with_image(prompt, shot)
        except Exception as e:
            transcript.append({"step": step, "error": f"vision: {e}"})
            break

        decision = _parse_decision(answer)
        transcript.append({"step": step, "decision": decision})
        if decision.get("done"):
            break

        tool_name = decision.get("tool")
        args = decision.get("args", {}) or {}
        try:
            await _dispatch(d, tool_name, args)
        except Exception as e:
            transcript.append({"step": step, "error": f"dispatch: {e}"})

    return json.dumps(
        {
            "goal": goal,
            "steps": len(transcript),
            "transcript_tail": transcript[-5:],
            "final_screenshot": str(shot),
        },
        indent=2,
        ensure_ascii=False,
    )


def _parse_decision(text: str) -> dict[str, Any]:
    """Pull a JSON object out of Gemini's reply. Tolerant of markdown fences."""
    import re
    # strip code fences
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


async def _dispatch(d: OnshapeDriver, tool: str | None, args: dict[str, Any]) -> None:
    """Route a tool call from the LLM into the right ui_actions function.
    Args come in flat from the model and are reshaped to function
    signatures. Unknown tools raise; the LLM shouldn't call things that
    aren't in the datasheet.
    """
    if not tool:
        return
    fn = TOOL_DISPATCH.get(tool)
    if fn is None:
        raise KeyError(f"unknown tool: {tool}")
    # Flatten xy pairs to tuples as required.
    return await fn(d, args)


# tool name -> coroutine(d, args) -> Result
async def _wrap_xy_pair(d: OnshapeDriver, args: dict[str, Any], x1: str, y1: str, x2: str, y2: str, fn):
    return await fn(d, (args[x1], args[y1]), (args[x2], args[y2]))


TOOL_DISPATCH: dict[str, Any] = {
    "view.fit": lambda d, a: ui_actions.view_fit(d),
    "view.top": lambda d, a: ui_actions.view_top(d),
    "sketch.start": lambda d, a: ui_actions.sketch_start(
        d, (a["plane_x"], a["plane_y"]) if "plane_x" in a and "plane_y" in a else None
    ),
    "sketch.rectangle": lambda d, a: ui_actions.sketch_rectangle(
        d, (a["corner1_x"], a["corner1_y"]), (a["corner2_x"], a["corner2_y"])
    ),
    "sketch.circle": lambda d, a: ui_actions.sketch_circle(
        d, (a["center_x"], a["center_y"]), a["radius_px"]
    ),
    "sketch.line": lambda d, a: ui_actions.sketch_line(
        d, (a["p1_x"], a["p1_y"]), (a["p2_x"], a["p2_y"])
    ),
    "sketch.exit": lambda d, a: ui_actions.sketch_exit(d),
    "feature.extrude": lambda d, a: ui_actions.feature_extrude(d, a.get("depth_mm")),
    "feature.fillet": lambda d, a: ui_actions.feature_fillet(d, a.get("radius_mm")),
    "feature.chamfer": lambda d, a: ui_actions.feature_chamfer(d, a.get("distance_mm")),
    "select.face": lambda d, a: ui_actions.select_face(d, a["x"], a["y"]),
    "select.edge": lambda d, a: ui_actions.select_edge(d, a["x"], a["y"]),
    "ui.undo": lambda d, a: ui_actions.undo(d),
    "ui.redo": lambda d, a: ui_actions.redo(d),
}


# ─── lifecycle ────────────────────────────────────────────────────────────

async def _cleanup() -> None:
    global _driver, _vision
    if _vision is not None:
        await _vision.close()
    if _driver is not None:
        await _driver.close()
    _driver = None
    _vision = None


def main() -> None:
    try:
        mcp.run()
    finally:
        asyncio.run(_cleanup())


if __name__ == "__main__":
    main()
