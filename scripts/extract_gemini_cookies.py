"""Extract Gemini cookies via a headed Playwright session.

Fallback path. The reliable one is scripts/extract_cookies_from_chrome.py
which reads your real Chrome session without launching a browser.

This script is here for when you don't have Chrome installed, or when
browser-cookie3 can't read your profile (e.g. macOS Keychain prompt).

What it does:
  1. Opens a headed browser pointing at gemini.google.com. Tries your
     installed real Chrome first (channel="chrome"), falls back to
     bundled Chromium.
  2. Waits for you to log in.
  3. Grabs __Secure-1PSID and __Secure-1PSIDTS from the context.
  4. Writes them to cookies/gemini.cookies.json.

Note: Google sometimes blocks automated browser logins with "This browser
or app may not be secure". If that happens, use the Chrome-session
extractor instead.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COOKIE_OUT = REPO_ROOT / "cookies" / "gemini.cookies.json"
GEMINI_HOME = "https://gemini.google.com"


async def main() -> int:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("playwright not installed. run scripts/bootstrap.py first.", file=sys.stderr)
        return 2

    profile_dir = REPO_ROOT / "playwright-profile-gemini"
    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"[extract_gemini_cookies] opening headed browser, profile={profile_dir}")
    print("[extract_gemini_cookies] log into gemini.google.com in the opened window.")
    print(
        "[extract_gemini_cookies] when you see the Gemini chat UI, come back here and press Enter."
    )

    async with async_playwright() as p:
        # Try your real Chrome first. Google blocks automated Chromium
        # but tends to allow real Chrome. Fall back to bundled Chromium
        # if Chrome isn't installed.
        ctx = None
        try:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                channel="chrome",
                viewport={"width": 1200, "height": 800},
            )
            print("[extract_gemini_cookies] using installed Chrome (channel=chrome)")
        except Exception as e:
            print(f"[extract_gemini_cookies] real Chrome unavailable ({e}); using bundled Chromium")
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                viewport={"width": 1200, "height": 800},
            )
        page = await ctx.new_page()
        await page.goto(GEMINI_HOME, wait_until="domcontentloaded")
        input("\n[extract_gemini_cookies] press Enter after you've logged in...\n")

        cookies = await ctx.cookies()
        psid = psidts = None
        for c in cookies:
            name = c.get("name", "")
            if name == "__Secure-1PSID":
                psid = c.get("value")
            elif name == "__Secure-1PSIDTS":
                psidts = c.get("value")

        if not (psid and psidts):
            print(
                "[extract_gemini_cookies] couldn't find __Secure-1PSID and "
                "__Secure-1PSIDTS in cookies. did the login complete?",
                file=sys.stderr,
            )
            await ctx.close()
            return 1

        COOKIE_OUT.parent.mkdir(parents=True, exist_ok=True)
        COOKIE_OUT.write_text(
            json.dumps(
                {
                    "secure_1psid": psid,
                    "secure_1psidts": psidts,
                    "_note": "extracted by scripts/extract_gemini_cookies.py",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[extract_gemini_cookies] wrote {COOKIE_OUT}")
        await ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
