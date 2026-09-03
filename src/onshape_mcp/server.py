"""MCP server entrypoint. Wires the driver, vision, journal, and tool datasheet
behind a small set of MCP tools. The actual UI ops are stubs in M0; they get
filled in as the datasheet tools move from `planned` to `working`.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import tools as datasheet
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


# ─── MCP tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def screenshot(name: str = "shot.png") -> str:
    """Take a screenshot of the current Onshape viewport. Returns the file path."""
    d = await _driver_lazy()
    path = await d.screenshot(name=name)
    entry = JournalEntry.new("screenshot", {"name": name})
    entry.screenshot = str(path.relative_to(settings.journal_dir.parent))
    journal.append(entry)
    return str(path)


@mcp.tool()
async def describe_view(question: str = "What do you see in the Onshape viewport?") -> str:
    """Screenshot + ask Gemini web to describe it. Returns the model's answer."""
    d = await _driver_lazy()
    img = await d.screenshot("describe.png")
    v = await _vision_lazy()
    text = await v.ask_with_image(question, img)
    return text


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


# Stubs for the datasheet tools — they record intent in the journal but don't
# drive the UI yet. The driver-side implementations land in the next milestones.
def _stub(name: str, args: dict[str, Any]) -> str:
    e = JournalEntry.new(name, args)
    e.result = "skipped"
    e.note = "M0 stub — UI op not implemented yet"
    journal.append(e)
    return f"{name}: stubbed (see journal)"


for _spec in datasheet.ALL_TOOLS:
    _name = _spec.name.replace(".", "_")

    def _make(name: str, _spec: datasheet.ToolSpec = _spec):
        @mcp.tool(name=f"onshape_{_name}")
        async def _tool(**kwargs: Any) -> str:
            return _stub(_spec.name, kwargs)
        return _tool

    _make(_name)


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
