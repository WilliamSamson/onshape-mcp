"""Configuration loaded from .env. The .env file is gitignored (see SECURITY.md)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the repo root, if present.
_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")


def _path(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (_REPO_ROOT / p).resolve()
    return p


class Settings:
    onshape_browser_profile: Path = _path(
        "ONSHAPE_BROWSER_PROFILE", "./playwright-profile"
    )
    gemini_cookie_file: Path = _path("GEMINI_COOKIE_FILE", "./cookies/gemini.cookies.json")
    journal_dir: Path = _path("JOURNAL_DIR", "./state")
    log_dir: Path = _path("LOG_DIR", "./logs")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    onshape_default_doc: str = os.getenv("ONSHAPE_DEFAULT_DOC", "")

    def __repr__(self) -> str:  # never leak cookie/profile paths into logs
        return (
            f"Settings(gemini_model={self.gemini_model!r}, "
            f"onshape_default_doc={self.onshape_default_doc!r})"
        )


settings = Settings()

# Make sure local-only directories exist.
for d in (settings.onshape_browser_profile, settings.journal_dir, settings.log_dir):
    d.mkdir(parents=True, exist_ok=True)
