"""Milestone 0: open Onshape, screenshot, dump viewport title. No vision, no LLM."""

from __future__ import annotations

import asyncio

from onshape_mcp.driver import OnshapeDriver


async def main() -> None:
    d = OnshapeDriver()
    await d.start(headless=True)
    await d.open()
    title = await d.page.title()
    url = d.page.url
    shot = await d.screenshot("m0_login.png")
    print(f"title : {title}")
    print(f"url   : {url}")
    print(f"shot  : {shot}")
    await d.close()


if __name__ == "__main__":
    asyncio.run(main())
