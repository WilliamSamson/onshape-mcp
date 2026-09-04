"""Configuration loaded from .env. The .env file is gitignored (see SECURITY.md)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _find_repo_root() -> Path:
    """Walk up from cwd looking for pyproject.toml. Works whether the
    package is being run from source or from an installed location inside
    a venv (the package's __file__ would otherwise point at site-packages).
    """
    cwd = Path.cwd()
    for p in [cwd, *cwd.parents]:
        if (p / "pyproject.toml").is_file():
            return p
    return cwd


_REPO_ROOT = _find_repo_root()
load_dotenv(_REPO_ROOT / ".env")


def _path(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    return p


def _bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # Onshape cookies live as plain JSON, not in Chrome's encrypted DB.
    # Chrome's DB on Linux uses a keyring key that's only available to
    # graphical sessions; headless Playwright can't decrypt, so cookies
    # look empty. Storing as JSON dodges the whole keyring mess.
    onshape_cookie_file: Path = _path("ONSHAPE_COOKIE_FILE", "./cookies/onshape.cookies.json")
    onshape_browser_profile: Path = _path("ONSHAPE_BROWSER_PROFILE", "./playwright-profile")
    gemini_cookie_file: Path = _path("GEMINI_COOKIE_FILE", "./cookies/gemini.cookies.json")
    journal_dir: Path = _path("JOURNAL_DIR", "./state")
    log_dir: Path = _path("LOG_DIR", "./logs")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-flash")
    gemini_temporary_chat: bool = _bool("GEMINI_TEMPORARY_CHAT", True)
    gemini_auto_cleanup: bool = _bool("GEMINI_AUTO_CLEANUP", True)
    onshape_default_doc: str = os.getenv("ONSHAPE_DEFAULT_DOC", "")
    # "auto" tries real Chrome first then bundled Chromium,
    # "chrome" requires real Chrome, "chromium" uses bundled Chromium only.
    browser_channel: str = os.getenv("ONSHAPE_BROWSER_CHANNEL", "auto")

    def __repr__(self) -> str:  # never leak cookie/profile paths into logs
        return (
            f"Settings(gemini_model={self.gemini_model!r}, "
            f"gemini_temporary_chat={self.gemini_temporary_chat}, "
            f"gemini_auto_cleanup={self.gemini_auto_cleanup}, "
            f"browser_channel={self.browser_channel!r}, "
            f"onshape_default_doc={self.onshape_default_doc!r})"
        )


settings = Settings()

# Make sure local-only directories exist.
for d in (
    settings.onshape_cookie_file.parent,
    settings.onshape_browser_profile,
    settings.gemini_cookie_file.parent,
    settings.journal_dir,
    settings.log_dir,
):
    d.mkdir(parents=True, exist_ok=True)
