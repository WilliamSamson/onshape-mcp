"""Gemini web client. Cookie-auth, no API key. Cookie file is gitignored
(see SECURITY.md). Cookie file format: {"secure_1psid": ..., "secure_1psidts": ...}.

I tried to keep the wrapper thin. The `gemini-webapi` package handles the
auth dance but its surface shifts often, so pin and verify on every
install.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .config import settings


class GeminiWeb:
    def __init__(self, cookie_file: Path | None = None, model: str | None = None) -> None:
        self.cookie_file = (cookie_file or settings.gemini_cookie_file).resolve()
        self.model = model or settings.gemini_model
        self._client: Any = None

    def _load_cookies(self) -> tuple[str, str]:
        data = json.loads(self.cookie_file.read_text(encoding="utf-8"))
        psid = data.get("secure_1psid") or data.get("__Secure-1PSID")
        psidts = data.get("secure_1psidts") or data.get("__Secure-1PSIDTS")
        if not (psid and psidts):
            raise ValueError(
                f"Cookie file {self.cookie_file} missing secure_1psid or "
                f"secure_1psidts. Re-export from your browser."
            )
        return psid, psidts

    async def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from gemini_webapi import GeminiClient  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "Install gemini-webapi: `pip install gemini-webapi`"
            ) from e
        psid, psidts = self._load_cookies()
        self._client = GeminiClient(psid, psidts, model=self.model)
        await self._client.init()

    async def ask_with_image(
        self, prompt: str, image_path: Path, timeout: int = 60
    ) -> str:
        await self._ensure_client()
        # The gemini-webapi client is sync-ish but exposes an async wrapper.
        chat = self._client.start_chat()
        response = await asyncio.wait_for(
            chat.send_message(prompt, files=[str(image_path)]),
            timeout=timeout,
        )
        return getattr(response, "text", str(response))

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
