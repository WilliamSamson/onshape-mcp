"""Playwright driver for Onshape. One headless Chromium, persistent
profile for cache, plain-JSON cookie file for the session.

Why JSON cookies instead of relying on Chrome's encrypted DB:
on Linux, Chrome encrypts cookies in its DB with a key from the system
keyring. The keyring is only available to graphical sessions, so
headless Playwright can't decrypt them; the cookies are present but
invisible. Storing them as plain JSON (and re-injecting via
`context.add_cookies()`) sidesteps the whole keyring issue.

Profile dir is gitignored (see SECURITY.md).

This module holds the lowest-level UI primitives. Higher-level Onshape
ops (sketch, extrude, fillet) live in ui_actions.py and compose these.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Locator, Page, async_playwright

from .config import settings

ONSHAPE_URL = "https://cad.onshape.com"


class OnshapeDriver:
    def __init__(
        self,
        profile_dir: Path | None = None,
        cookie_file: Path | None = None,
    ) -> None:
        self.profile_dir = (profile_dir or settings.onshape_browser_profile).resolve()
        self.cookie_file = (cookie_file or settings.onshape_cookie_file).resolve()
        self.channel = settings.browser_channel
        self._pw: Any = None
        self._ctx: BrowserContext | None = None
        self._page: Page | None = None

    async def start(self, headless: bool = True) -> Page:
        self._pw = await async_playwright().start()
        self._clear_stale_locks()
        # We use the profile dir mainly for the SingletonLock dance and
        # any future extensions we might want to install. Cache is not
        # worth the stale-state headaches, so we use a non-persistent
        # context when possible. Cookies live in self.cookie_file (plain
        # JSON) and get injected after launch — no need for the profile
        # to carry the session.
        #
        # Channel strategy: try real Chrome first (no automation markers,
        # dodges Google's "this browser may not be secure" block). Fall
        # back to bundled Chromium. Set ONSHAPE_BROWSER_CHANNEL=chromium
        # to skip the Chrome attempt (e.g. on a Pi with no Chrome).
        #
        # WebGL args: Onshape renders the 3D viewport with WebGL. In
        # headless mode we need to ask explicitly for software WebGL or
        # the canvas stays blank. `swiftshader` is Google's software
        # WebGL implementation and works on any machine.
        common_args = [
            "--use-gl=swiftshader",
            "--enable-webgl",
            "--ignore-gpu-blocklist",
            "--disable-blink-features=AutomationControlled",
        ]
        if self.channel in ("auto", "chrome"):
            try:
                self._ctx = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    args=common_args,
                    channel="chrome",
                )
                self._channel_used = "chrome"
            except Exception as e:
                if self.channel == "chrome":
                    raise
                print(f"[driver] real Chrome unavailable ({e}); using bundled Chromium")
                self._ctx = await self._pw.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=headless,
                    viewport={"width": 1440, "height": 900},
                    args=common_args,
                )
                self._channel_used = "chromium"
        else:
            self._ctx = await self._pw.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=headless,
                viewport={"width": 1440, "height": 900},
                args=common_args,
            )
            self._channel_used = "chromium"
        await self._load_cookies()
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()
        return self._page

    def _clear_stale_locks(self) -> None:
        """Remove leftover SingletonLock/SingletonCookie files from prior
        Chrome runs. Without this, a crashed previous run blocks all
        subsequent launches of the same profile.
        """
        for fname in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            p = self.profile_dir / fname
            if p.exists():
                try:
                    p.unlink()
                except OSError:
                    pass

    async def _load_cookies(self) -> None:
        """Re-inject saved cookies into the context before any navigation.
        Without this, even a logged-in session looks anonymous because
        Chrome's encrypted DB can't be read headless.
        """
        raw = []
        # 1. Environment variable support (useful for remote/cloud hosting)
        env_cookies = os.getenv("ONSHAPE_COOKIES_JSON")
        if env_cookies:
            try:
                raw = json.loads(env_cookies)
            except Exception as e:
                print(f"[driver] failed parsing ONSHAPE_COOKIES_JSON: {e}")

        # 2. Local cookie file
        if not raw and self.cookie_file.exists():
            try:
                raw = json.loads(self.cookie_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                print(f"[driver] cookie file unreadable ({e}); ignoring")

        # 3. Auto-extract from available installed browsers
        if not raw:
            try:
                import browser_cookie3

                browser_loaders = [
                    ("Chrome", getattr(browser_cookie3, "chrome", None)),
                    ("Brave", getattr(browser_cookie3, "brave", None)),
                    ("Edge", getattr(browser_cookie3, "edge", None)),
                    ("Chromium", getattr(browser_cookie3, "chromium", None)),
                    ("Firefox", getattr(browser_cookie3, "firefox", None)),
                    ("Arc", getattr(browser_cookie3, "arc", None)),
                    ("Opera", getattr(browser_cookie3, "opera", None)),
                    ("Vivaldi", getattr(browser_cookie3, "vivaldi", None)),
                ]
                for browser_name, loader in browser_loaders:
                    if loader is None:
                        continue
                    try:
                        cj = loader(domain_name="onshape.com")
                        for c in cj:
                            cookie = {
                                "name": c.name,
                                "value": c.value,
                                "domain": c.domain,
                                "path": c.path,
                                "secure": bool(c.secure),
                                "httpOnly": bool(
                                    c.has_nonstandard_attr("HttpOnly")
                                    or c.has_nonstandard_attr("httponly")
                                ),
                            }
                            if c.expires:
                                cookie["expires"] = float(c.expires)
                            raw.append(cookie)
                        if raw:
                            self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
                            self.cookie_file.write_text(json.dumps(raw, indent=2), encoding="utf-8")
                            print(
                                f"[driver] auto-synced {len(raw)} Onshape cookies from {browser_name} to {self.cookie_file.name}"
                            )
                            break
                    except Exception:
                        continue
            except Exception as e:
                print(f"[driver] could not extract Onshape cookies from local browsers: {e}")
        if not raw:
            return
        # Playwright's add_cookies wants the same shape it returns.
        await self._ctx.add_cookies(raw)
        print(f"[driver] loaded {len(raw)} cookies from {self.cookie_file.name}")

    async def save_cookies(self) -> int:
        """Dump current context cookies to self.cookie_file. Returns count."""
        cookies = await self._ctx.cookies()
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookie_file.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        return len(cookies)

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Driver not started; call .start() first")
        return self._page

    @property
    def channel_used(self) -> str:
        return getattr(self, "_channel_used", "unknown")

    async def open(self, url: str | None = None) -> None:
        if not url:
            if settings.onshape_default_doc:
                doc = settings.onshape_default_doc
                url = (
                    doc if doc.startswith("http") else f"https://cad.onshape.com/{doc.lstrip('/')}"
                )
            else:
                url = ONSHAPE_URL
        # Onshape is a SPA that keeps WebSocket connections open, so
        # `networkidle` never fires (it would time out at 60s). We use
        # `load` for the navigation then `wait_for_app()` to confirm the
        # toolbar is actually on screen.
        await self.page.goto(url, wait_until="load", timeout=60_000)
        await self.wait_for_app()
        if "signin" in self.page.url:
            raise RuntimeError(
                "Onshape redirected to signin page. Cookies may be invalid or expired. "
                "Please log in to cad.onshape.com in Google Chrome."
            )

    # Screenshots

    async def wait_for_app(self, timeout: float = 30.0) -> bool:
        """Wait until the Onshape app shell has rendered something we can
        see. The marker is broad: any toolbar button, the documents list,
        a sketch button, whatever the current page has. Returns True if
        something rendered, False if the page is still blank after the
        timeout. Either way we sleep an extra beat for the WebGL canvas.
        """
        try:
            await self.page.wait_for_function(
                """() => {
                    // any rendered buttons with visible text or aria-label
                    const btns = document.querySelectorAll('button, [role="button"], a, .document-card, .document-list-item');
                    let n = 0;
                    for (const b of btns) {
                        const t = (b.textContent || b.getAttribute('aria-label') || '').trim();
                        if (t.length > 0) n++;
                        if (n >= 3) return true;
                    }
                    // any substantial content (h1-h3, paragraphs, etc.)
                    const text = document.body.innerText || '';
                    return text.length > 100;
                }""",
                timeout=timeout * 1000,
            )
            # Wait for graphics / loading spinner to clear
            try:
                await self.page.locator(".loading-progress-message").wait_for(
                    state="hidden", timeout=30_000
                )
            except Exception:
                pass
            await asyncio.sleep(1.0)
            return True
        except Exception:
            return False

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
        return await self.page.evaluate("() => ({w: window.innerWidth, h: window.innerHeight})")

    # Clicks and drags

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

    # Keyboard input

    async def type_text(self, text: str, delay_ms: int = 10) -> None:
        await self.page.keyboard.type(text, delay=delay_ms)

    async def press_key(self, key: str) -> None:
        """Press a single key. e.g. 'Enter', 'Escape', 'Tab'."""
        await self.page.keyboard.press(key)

    async def press_chord(self, *keys: str) -> None:
        """Press a key combination, e.g. press_chord('Control', 'z')."""
        combo = "+".join(keys)
        await self.page.keyboard.press(combo)

    # Element finding
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
        strategies.append(
            self.page.locator(f"[aria-label*='{text}']" if partial else f"[aria-label='{text}']")
        )
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

    # Lifecycle

    async def close(self) -> None:
        if self._ctx is not None:
            await self._ctx.close()
        if self._pw is not None:
            await self._pw.stop()
        self._ctx = None
        self._page = None
        self._pw = None


async def login_interactive() -> None:
    """Open a headed browser, let the user log in, then dump the session
    cookies to self.cookie_file. Subsequent headless runs re-inject them.
    """
    d = OnshapeDriver()
    await d.start(headless=False)
    await d.open(ONSHAPE_URL)
    print("Log into Onshape in the opened browser, then press Enter here.")
    input("> ")
    n = await d.save_cookies()
    print(f"Saved {n} cookies to {d.cookie_file}")
    await d.close()


def main() -> None:
    """`python -m onshape_mcp.driver login`"""
    import sys

    if len(sys.argv) >= 2 and sys.argv[1] == "login":
        asyncio.run(login_interactive())
    else:
        print("usage: python -m onshape_mcp.driver login")


if __name__ == "__main__":
    main()
