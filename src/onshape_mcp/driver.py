"""Playwright driver for Onshape web.

Single headless Chromium instance, persistent profile so the user stays
logged in across runs. The profile dir is gitignored — see SECURITY.md.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright

from .config import settings

ONSHAPE_URL = "https://cad.onshape.com"


class OnshapeDriver:
    def __init__(self, profile_dir: Path | None = None) -> None:
        self.profile_dir = (profile_dir or settings.onshape_browser_profile).resolve()
        self._pw: Any = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self, headless: bool = True) -> Page:
        self._pw = await async_playwright().start()
        # Persistent context: cookies + local storage live on disk,
        # so a single `login` keeps you signed in forever.
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=headless,
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._page = await self._ctx.new_page()
        return self._page

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Driver not started — call .start() first")
        return self._page

    async def open(self, url: str = ONSHAPE_URL) -> None:
        await self.page.goto(url, wait_until="domcontentloaded")

    async def screenshot(self, name: str = "shot.png") -> Path:
        out = settings.journal_dir / name
        out.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(out), full_page=False)
        return out

    async def close(self) -> None:
        if self._ctx is not None:
            await self._ctx.close()
        if self._pw is not None:
            await self._pw.stop()
        self._ctx = None
        self._page = None
        self._pw = None


async def login_interactive() -> None:
    """Open a headed browser, let the user log in, then close. The persistent
    profile means subsequent headless runs stay signed in.
    """
    d = OnshapeDriver()
    page = await d.start(headless=False)
    await d.open(ONSHAPE_URL)
    print("Log into Onshape in the opened browser, then press Enter here.")
    input("> ")
    await d.close()
    print(f"Session saved to {d.profile_dir}")


def main() -> None:
    """`python -m onshape_mcp.driver login`"""
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "login":
        asyncio.run(login_interactive())
    else:
        print("usage: python -m onshape_mcp.driver login")


if __name__ == "__main__":
    main()
