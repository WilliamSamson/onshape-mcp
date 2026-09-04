"""Gemini web client. Cookie-auth, no API key. Cookie file is gitignored
(see SECURITY.md). Cookie file format: {"secure_1psid": ..., "secure_1psidts": ...}.

I tried to keep the wrapper thin. The `gemini-webapi` package handles the
auth dance but its surface shifts often, so pin and verify on every
install.

The library supports two cookie paths: pass them explicitly, or let it
use browser-cookie3 to read straight from Chrome. The latter is more
robust because it grabs the full session (PSID, PSIDTS, PSIDCC, plus
the third-party cookies) and uses the keyring to decrypt. Explicit
cookies can fail for the multimodal endpoint even when text chat works,
because the image-upload path validates against more cookies.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .config import settings


class GeminiWeb:
    def __init__(
        self,
        cookie_file: Path | None = None,
        model: str | None = None,
        temporary: bool | None = None,
        auto_cleanup: bool | None = None,
    ) -> None:
        self.cookie_file = (cookie_file or settings.gemini_cookie_file).resolve()
        self.model = model or settings.gemini_model
        self.temporary = settings.gemini_temporary_chat if temporary is None else temporary
        self.auto_cleanup = settings.gemini_auto_cleanup if auto_cleanup is None else auto_cleanup
        self._client: Any = None
        self._active_session: Any = None
        self.created_chat_ids: set[str] = set()

    def _has_cookie_file(self) -> bool:
        """True if the cookie file exists and has the two required values."""
        if not self.cookie_file.exists():
            return False
        try:
            data = json.loads(self.cookie_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        psid = data.get("secure_1psid") or data.get("__Secure-1PSID")
        psidts = data.get("secure_1psidts") or data.get("__Secure-1PSIDTS")
        return bool(psid and psidts)

    async def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            from gemini_webapi import GeminiClient  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("Install gemini-webapi: `pip install gemini-webapi`") from e

        # Prefer letting the library use browser-cookie3 directly. It
        # grabs the full Chrome session (PSID, PSIDTS, PSIDCC, third-party
        # cookies) and decrypts via the keyring, which is the path that
        # works for the multimodal (image upload) endpoint.
        psid = psidts = None
        if self._has_cookie_file():
            data = json.loads(self.cookie_file.read_text(encoding="utf-8"))
            psid = data.get("secure_1psid") or data.get("__Secure-1PSID")
            psidts = data.get("secure_1psidts") or data.get("__Secure-1PSIDTS")
            # Try the explicit path first. If image upload fails we'll
            # fall back to browser-cookie3.
            self._client = GeminiClient(psid, psidts, model=self.model)
            try:
                await self._client.init(timeout=30)
                return
            except Exception as e:
                print(
                    f"[vision] explicit-cookie init failed ({e}); falling back to browser-cookie3"
                )
                try:
                    await self._client.close()
                except Exception:
                    pass
                self._client = None

        # Fallback: empty client -> library reads Chrome directly.
        self._client = GeminiClient(None, None, model=self.model)
        await self._client.init(timeout=30)

    async def _refresh_cookies_from_chrome(self) -> bool:
        """Re-extract Gemini cookies from the user's real Chrome. The
        gemini-webapi library doesn't refresh its session automatically
        and the cookies can go stale between calls. This pulls fresh
        ones and overwrites the cookie file.
        """
        try:
            import browser_cookie3
        except ImportError:
            return False
        try:
            cj = browser_cookie3.chrome(domain_name="google.com")
        except Exception as e:
            print(f"[vision] could not read Chrome cookies: {e}")
            return False
        psid = psidts = None
        for c in cj:
            if c.name == "__Secure-1PSID":
                psid = c.value
            elif c.name == "__Secure-1PSIDTS":
                psidts = c.value
        if not (psid and psidts):
            return False
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookie_file.write_text(
            json.dumps(
                {
                    "secure_1psid": psid,
                    "secure_1psidts": psidts,
                    "_note": "refreshed by vision.py",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return True

    async def new_session(self, temporary: bool | None = None) -> Any:
        """Create and track a new ChatSession attached to this client."""
        await self._ensure_client()
        session = self._client.start_chat()
        self._session_temporary = self.temporary if temporary is None else temporary
        self._active_session = session
        return session

    def get_session(self) -> Any:
        """Return the active ChatSession, if any."""
        return self._active_session

    def reset_session(self) -> None:
        """Clear the active ChatSession."""
        self._active_session = None

    async def delete_chat(self, cid: str) -> bool:
        """Delete a specific conversation by chat ID. Returns True if successful."""
        await self._ensure_client()
        try:
            await self._client.delete_chat(cid)
            self.created_chat_ids.discard(cid)
            print(f"[vision] deleted chat {cid}")
            return True
        except Exception as e:
            print(f"[vision] failed to delete chat {cid}: {e}")
            return False

    async def list_chats(self) -> list[Any]:
        """List all conversations in the user's Gemini account."""
        await self._ensure_client()
        try:
            res = self._client.list_chats()
            return res or []
        except Exception as e:
            print(f"[vision] failed to list chats: {e}")
            return []

    async def cleanup_created_chats(self) -> int:
        """Delete all non-temporary chats created and tracked by this instance."""
        if not self.created_chat_ids or self._client is None:
            return 0
        to_delete = list(self.created_chat_ids)
        deleted = 0
        for cid in to_delete:
            if await self.delete_chat(cid):
                deleted += 1
        return deleted

    async def ask_with_image(
        self,
        prompt: str,
        image_path: Path,
        session: Any = None,
        temporary: bool | None = None,
        timeout: int = 120,
    ) -> str:
        # Try up to 2 times. If the first call hits an "UNAUTHENTICATED"
        # error, re-extract cookies from Chrome (they go stale) and
        # re-initialise the client.
        last_err: Exception | None = None
        use_temp = (
            getattr(self, "_session_temporary", self.temporary) if temporary is None else temporary
        )

        for attempt in range(2):
            await self._ensure_client()
            if attempt > 0:
                chat = self._client.start_chat()
                self._active_session = chat
            else:
                chat = session or self._active_session
                if chat is None:
                    chat = self._client.start_chat()
                    self._active_session = chat

            temp_flag = use_temp
            try:
                response = await asyncio.wait_for(
                    chat.send_message(prompt, files=[str(image_path)], temporary=temp_flag),
                    timeout=timeout,
                )
                cid = getattr(chat, "cid", None)
                if cid and not temp_flag:
                    self.created_chat_ids.add(cid)
                return getattr(response, "text", str(response))
            except Exception as e:
                last_err = e
                if "UNAUTHENTICATED" in str(e) or "Permission" in str(e):
                    print(f"[vision] auth error on attempt {attempt + 1}: {e}")
                    try:
                        await self._client.close()
                    except Exception:
                        pass
                    self._client = None
                    self._active_session = None
                    if attempt == 0:
                        print("[vision] re-extracting cookies from Chrome")
                        if not await self._refresh_cookies_from_chrome():
                            print(
                                "[vision] cookie refresh failed; will retry with whatever we have"
                            )
                        continue
                raise
        raise last_err if last_err else RuntimeError("vision: unknown failure")

    async def close(self) -> None:
        if self.auto_cleanup and self.created_chat_ids:
            try:
                await self.cleanup_created_chats()
            except Exception as e:
                print(f"[vision] error during auto-cleanup: {e}")
        self._active_session = None
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
            self._client = None
