"""Version reporting and self-update, exposed as MCP tools.

With a stable tunnel hostname the connector URL never changes, so the
server can pull new code and restart itself without anyone re-pasting a
URL into ChatGPT. That is the whole point of pairing this with
ONSHAPE_TUNNEL_SUBDOMAIN.

Registers onto the server's existing FastMCP instance on import, so
server.py does not need to know this module exists.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .config import _BASE_DIR
from .server import mcp

REPO = Path(_BASE_DIR)


def _git(*args: str, timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:  # git missing, not a repo, network down
        return 1, f"{type(e).__name__}: {e}"


def _describe() -> dict:
    code, head = _git("rev-parse", "--short", "HEAD")
    _, subject = _git("log", "-1", "--pretty=%s")
    _, dirty = _git("status", "--porcelain")
    return {
        "commit": head if code == 0 else "unknown",
        "subject": subject,
        "uncommitted_changes": bool(dirty),
        "repo": str(REPO),
    }


@mcp.tool()
async def onshape_mcp_version() -> str:
    """Report the running server's version and whether an update is available.

    Call this first when a tool behaves unexpectedly — the server may be
    running older code than the repository.
    """
    info = _describe()
    fetch_code, fetch_out = _git("fetch", "--quiet", "origin", "main")
    if fetch_code == 0:
        _, behind = _git("rev-list", "--count", "HEAD..origin/main")
        info["commits_behind_main"] = int(behind) if behind.isdigit() else None
        info["update_available"] = bool(info["commits_behind_main"])
    else:
        info["update_available"] = None
        info["fetch_error"] = fetch_out[:200]
    info["ok"] = True
    return json.dumps(info, indent=2)


@mcp.tool()
async def onshape_mcp_update(restart: bool = False) -> str:
    """Pull the latest code from origin/main.

    New code only takes effect once the process restarts. Pass
    restart=True to have the server restart itself — safe only behind a
    stable tunnel hostname, since the URL must survive the restart.
    Refuses to discard uncommitted work.
    """
    before = _describe()
    if before["uncommitted_changes"]:
        return json.dumps(
            {
                "ok": False,
                "error": "uncommitted changes present",
                "message": "Refusing to pull over uncommitted work. Commit or stash first.",
                **before,
            },
            indent=2,
        )

    code, out = _git("pull", "--ff-only", "origin", "main", timeout=180)
    if code != 0:
        return json.dumps(
            {"ok": False, "error": "git pull failed", "detail": out[:500], **before}, indent=2
        )

    after = _describe()
    changed = before["commit"] != after["commit"]
    result = {
        "ok": True,
        "updated": changed,
        "from": before["commit"],
        "to": after["commit"],
        "now_running": after["subject"],
        "restart_required": changed and not restart,
    }
    if changed and restart:
        result["message"] = (
            "Restarting now. Reconnect in ~15s — the tunnel URL does not change."
        )
        _schedule_restart()
    elif changed:
        result["message"] = (
            "Pulled. The running process still has the old code; "
            "call onshape_mcp_update(restart=True) or restart it manually."
        )
    else:
        result["message"] = "Already up to date."
    return json.dumps(result, indent=2)


def _schedule_restart() -> None:
    """Re-exec this process shortly, after the response has been sent."""
    import threading

    def go() -> None:
        import time

        time.sleep(1.5)  # let the JSON-RPC reply flush to the client
        os.execv(sys.executable, [sys.executable, *sys.argv])

    threading.Thread(target=go, daemon=True).start()
