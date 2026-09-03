"""Milestone 0: open Onshape, wait for the app shell to render, screenshot.

No vision, no LLM. Just proves that headless Chrome + WebGL is actually
showing the Onshape UI, not a blank white page.
"""

from __future__ import annotations

import asyncio
import sys

from onshape_mcp.driver import OnshapeDriver


async def main() -> int:
    d = OnshapeDriver()
    await d.start(headless=True)
    await d.open()
    title = await d.page.title()
    url = d.page.url
    ready = await d.wait_for_app(timeout=30.0)
    shot = await d.screenshot("m0_login.png")
    channel = d.channel_used
    print(f"title   : {title}")
    print(f"url     : {url}")
    print(f"channel : {channel}")
    print(f"app     : {'ready' if ready else 'NOT READY (blank screenshot likely)'}")
    print(f"shot    : {shot}")
    await d.close()
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
