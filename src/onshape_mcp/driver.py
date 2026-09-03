"""Playwright driver for Onshape web.

Single headless Chromium instance, persistent profile so the user stays
logged in across runs. The profile dir is gitignored — see SECURITY.md.

This module holds the *lowest-level* UI primitives. Higher-level Onshape
ops (sketch, extrude, fillet) live in `ui_actions.py` and compose these.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Locator, Page, async_playwright

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

    # ─── screenshots ─────────────────────────────────────────────────────

    async def screenshot(self, name: str = "shot.png") -> Path:
        out = settings.journal_dir / name
        out.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(out), full_page=False)
        return out

    async def screenshot_clip(self, name: str, rect: dict[str, float]) -> Path:
        out = settings.journal_dir / name
        out.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(out), clip=rect)
        return out

    async def viewport_box(self) -> dict[str, float]:
        return await self.page.evaluate(
            "() => ({w: window.innerWidth, h: window.innerHeight})"
        )

    # ─── clicks / drags ──────────────────────────────────────────────────

    async def click(
        self,
        x: float,
        y: float,
        button: str = "left",
        click_count: int = 1,
    ) -> None:
        await self.page.mouse.click(x, y, button=button, click_count=click_count)

    async def double_click(self, x: float, y: float) -> None:
        await self.click(x, y, click_count=2)

    async def drag(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        steps: int = 10,
        button: str = "left",
    ) -> None:
        sx, sy = start
        ex, ey = end
        await self.page.mouse.move(sx, sy)
        await self.page.mouse.down(button=button)
        await self.page.mouse.move(ex, ey, steps=steps)
        await self.page.mouse.up(button=button)

    async def hover(self, x: float, y: float) -> None:
        await self.page.mouse.move(x, y)

    # ─── keyboard ────────────────────────────────────────────────────────

    async def type_text(self, text: str, delay_ms: int = 10) -> None:
        await self.page.keyboard.type(text, delay=delay_ms)

    async def press_key(self, key: str) -> None:
        """Press a single key. e.g. 'Enter', 'Escape', 'Tab'."""
        await self.page.keyboard.press(key)

    async def press_chord(self, *keys: str) -> None:
        """Press a key combination, e.g. press_chord('Control', 'z')."""
        combo = "+".join(keys)
        await self.page.keyboard.press(combo)

    # ─── element finding ─────────────────────────────────────────────────
    # Most of the Onshape UI is canvas + custom DOM, so text/aria selectors
    # are the most reliable. We try a few strategies and return the first hit.

    async def find_by_text(
        self,
        text: str,
        *,
        partial: bool = True,
        role: str | None = None,
        timeout_ms: int = 3000,
    ) -> Locator | None:
        """Return a locator matching the given visible text (or aria-label).

        Returns None if not found within timeout. Caller decides whether to
        click, get the box, etc.
        """
        strategies: list[Locator] = []
        if role:
            strategies.append(self.page.get_by_role(role, name=text, exact=not partial))
        # aria-label / title
        strategies.append(self.page.locator(f"[aria-label*='{text}']" if partial else f"[aria-label='{text}']"))
        # visible text content
        strategies.append(self.page.get_by_text(text, exact=not partial))
        for loc in strategies:
            try:
                if await loc.first.is_visible(timeout=timeout_ms / 1000):
                    return loc.first
            except Exception:
                continue
        return None

    async def click_text(
        self,
        text: str,
        *,
        partial: bool = True,
        timeout_ms: int = 3000,
    ) -> bool:
        loc = await self.find_by_text(text, partial=partial, timeout_ms=timeout_ms)
        if loc is None:
            return False
        await loc.click()
        return True

    async def wait_for_text(self, text: str, timeout: float = 5.0) -> bool:
        try:
            await self.page.get_by_text(text).first.wait_for(timeout=timeout * 1000)
            return True
        except Exception:
            return False

    async def wait_for_no_text(self, text: str, timeout: float = 5.0) -> bool:
        """True if the text disappears within timeout. False if it's still there."""
        try:
            await self.page.get_by_text(text).first.wait_for(state="hidden", timeout=timeout * 1000)
            return True
        except Exception:
            return False

    # ─── lifecycle ───────────────────────────────────────────────────────

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
