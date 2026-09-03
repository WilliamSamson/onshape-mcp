"""Extract Gemini cookies from the user's real Chrome session.

This is the reliable path. Google blocks automated browsers ("This browser
or app may not be secure") when Playwright launches bundled Chromium, but
it doesn't block your everyday Chrome. So we read the cookies straight
out of Chrome's local profile.

How it works:
  1. You log into gemini.google.com in your regular Chrome (once).
  2. Run this script. It reads Chrome's cookies SQLite DB.
  3. It writes __Secure-1PSID and __Secure-1PSIDTS to
     cookies/gemini.cookies.json in the format vision.py expects.

If Chrome is currently running it usually still works, but if you get
permission errors, close Chrome and rerun.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COOKIE_OUT = REPO_ROOT / "cookies" / "gemini.cookies.json"


def main() -> int:
    try:
        import browser_cookie3
    except ImportError:
        print(
            "browser-cookie3 not installed. run: pip install browser-cookie3",
            file=sys.stderr,
        )
        return 2

    print("[extract_cookies_from_chrome] reading cookies from your Chrome profile")
    try:
        cj = browser_cookie3.chrome(domain_name="google.com")
    except Exception as e:
        print(
            f"[extract_cookies_from_chrome] could not read Chrome cookies: {e}\n"
            "If Chrome is open, try closing it and rerunning.\n"
            "On macOS you may need to allow Keychain access.",
            file=sys.stderr,
        )
        return 1

    psid = psidts = None
    for c in cj:
        if c.name == "__Secure-1PSID":
            psid = c.value
        elif c.name == "__Secure-1PSIDTS":
            psidts = c.value

    if not (psid and psidts):
        print(
            "[extract_cookies_from_chrome] didn't find __Secure-1PSID /\n"
            "__Secure-1PSIDTS. Have you visited gemini.google.com and\n"
            "logged in in Chrome?",
            file=sys.stderr,
        )
        return 1

    COOKIE_OUT.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_OUT.write_text(
        json.dumps(
            {
                "secure_1psid": psid,
                "secure_1psidts": psidts,
                "_note": "extracted by scripts/extract_cookies_from_chrome.py",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[extract_cookies_from_chrome] wrote {COOKIE_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
