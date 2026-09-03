"""One-shot setup. Idempotent. Re-run any time.

Usage:
    python scripts/bootstrap.py

What it does:
  1. Checks Python version (needs 3.11+).
  2. Creates .venv/ if missing.
  3. Installs deps from requirements.txt into the venv.
  4. Runs `playwright install chromium` (downloads the browser).
  5. Copies .env.example to .env if .env doesn't exist.
  6. Runs scripts/extract_gemini_cookies.py to grab Gemini cookies.
  7. Runs `python -m onshape_mcp.driver login` for the Onshape session.
  8. Runs scripts/m0_login.py + scripts/m0_gemini.py as sanity checks.

If you call this from outside the venv, it re-execs itself inside the venv
so pip / playwright go to the right place. Print messages are minimal on
purpose: this is for me, not for newcomers.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV = REPO_ROOT / ".venv"
VENV_PY = VENV / "bin" / "python"  # POSIX; we don't support Windows yet
REQUIRED_MAJOR = 3
REQUIRED_MINOR = 11


def _inside_venv() -> bool:
    return sys.prefix == str(VENV.resolve())


def _ensure_venv() -> None:
    if VENV.exists():
        return
    print(f"[bootstrap] creating venv at {VENV}")
    venv.EnvBuilder(with_pip=True, upgrade_deps=True).create(str(VENV))


def _reexec_in_venv() -> None:
    if _inside_venv():
        return
    _ensure_venv()
    print(f"[bootstrap] re-running inside venv: {VENV_PY}")
    os.execv(str(VENV_PY), [str(VENV_PY), __file__, *sys.argv[1:]])


def _run(label: str, cmd: list[str], check: bool = True) -> None:
    print(f"\n[bootstrap] {label}\n  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if check and result.returncode != 0:
        raise SystemExit(f"[bootstrap] {label} failed (exit {result.returncode})")


def _pip_install() -> None:
    _run("pip install -r requirements.txt",
         [str(VENV_PY), "-m", "pip", "install", "--upgrade", "pip", "wheel"],
         check=False)
    _run("pip install -r requirements.txt",
         [str(VENV_PY), "-m", "pip", "install", "-r", "requirements.txt"])


def _playwright_install() -> None:
    _run("playwright install chromium",
         [str(VENV_PY), "-m", "playwright", "install", "chromium"])


def _ensure_env_file() -> None:
    env = REPO_ROOT / ".env"
    example = REPO_ROOT / ".env.example"
    if env.exists():
        print(f"[bootstrap] .env already exists at {env} (leaving alone)")
        return
    env.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[bootstrap] created {env} from .env.example")
    print("[bootstrap] edit it if you want non-default paths, then re-run this script")


def _extract_gemini_cookies() -> None:
    cookie_file = REPO_ROOT / "cookies" / "gemini.cookies.json"
    if cookie_file.exists() and cookie_file.stat().st_size > 0:
        print(f"[bootstrap] Gemini cookies already at {cookie_file} (skipping)")
        return

    # Preferred path: read cookies straight from the user's real Chrome
    # session. No browser launch, so Google's anti-automation block
    # doesn't fire.
    print("[bootstrap] trying Chrome-session cookie extraction first")
    result = subprocess.run(
        [str(VENV_PY), str(REPO_ROOT / "scripts" / "extract_cookies_from_chrome.py")],
        cwd=str(REPO_ROOT),
    )
    if result.returncode == 0 and cookie_file.exists():
        return

    # Fallback: headed Playwright (real Chrome if available, bundled
    # Chromium otherwise). User has to log in manually.
    print("[bootstrap] Chrome-session extraction failed; falling back to headed Playwright")
    _run("extract_gemini_cookies.py",
         [str(VENV_PY), str(REPO_ROOT / "scripts" / "extract_gemini_cookies.py")])


def _onshape_login() -> None:
    profile = REPO_ROOT / "playwright-profile"
    if profile.exists() and any(profile.iterdir()):
        print(f"[bootstrap] Onshape profile already at {profile} (skipping login)")
        return
    print("[bootstrap] need to log into Onshape (one-time, headed)")
    _run("onshape login",
         [str(VENV_PY), "-m", "onshape_mcp.driver", "login"])


def _m0_sanity() -> None:
    print("\n[bootstrap] running M0 sanity checks\n")
    _run("m0_login.py", [str(VENV_PY), "scripts/m0_login.py"], check=False)
    img = REPO_ROOT / "state" / "describe.png"
    if img.exists():
        _run("m0_gemini.py", [str(VENV_PY), "scripts/m0_gemini.py", str(img)], check=False)


def main() -> None:
    major, minor = sys.version_info[:2]
    if (major, minor) < (REQUIRED_MAJOR, REQUIRED_MINOR):
        raise SystemExit(f"need Python {REQUIRED_MAJOR}.{REQUIRED_MINOR}+, got {major}.{minor}")

    _reexec_in_venv()

    _pip_install()
    _playwright_install()
    _ensure_env_file()
    _extract_gemini_cookies()
    _onshape_login()
    _m0_sanity()

    print("\n[bootstrap] done. next: source .venv/bin/activate && python -m onshape_mcp.server")


if __name__ == "__main__":
    main()
