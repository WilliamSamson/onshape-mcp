"""`onshape-mcp up` — one command that gets you a working connector URL.

Everything this does was previously a separate manual step, and every one
of them has failed in practice:

  * stale servers and orphaned tunnel processes left the port busy, or
    worse, left a public hostname alive with nothing behind it (502)
  * a cookie file full of unexpired-but-revoked cookies looked fine to
    every check that only counted cookies
  * the session died silently and only surfaced as a tool error later

So this checks the things that actually break, fixes what it can, and
refuses to print a URL it has not proven works.
"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys

from .config import settings
from .tunnel import _port_is_free, _ngrok_domain, _stable_subdomain, find_tunnel_binary


def _say(ok: bool | None, msg: str) -> None:
    print(f"  {'✓' if ok else '⚠' if ok is None else '✗'} {msg}", flush=True)


def _running_strays(port: int) -> list[tuple[int, str]]:
    """Our own leftovers: MCP servers and tunnels, excluding this process."""
    if platform.system() == "Windows":
        return []
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,args="], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return []
    me = {os.getpid(), os.getppid()}
    found = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_str, _, args = line.partition(" ")
        if not pid_str.isdigit():
            continue
        pid = int(pid_str)
        if pid in me or "onshape-mcp up" in args or " up" == args[-3:]:
            continue
        hit = (
            "onshape_mcp.server share" in args
            or "onshape-mcp share" in args
            or ("cloudflared" in args and "tunnel" in args)
            or "localtunnel" in args
            or ("ngrok" in args and "http" in args)
        )
        if hit:
            found.append((pid, args[:70]))
    return found


def _clear_strays(port: int) -> None:
    strays = _running_strays(port)
    if not strays:
        _say(True, "no stale servers or tunnels")
        return
    for pid, args in strays:
        try:
            os.kill(pid, 15)
            _say(True, f"stopped stale process {pid} ({args})")
        except Exception as e:
            _say(False, f"could not stop {pid}: {e}")
    # A tunnel that outlives its server keeps a public hostname alive with
    # nothing behind it, which is exactly how a 502 happens.
    import time

    time.sleep(2)
    for pid, _ in _running_strays(port):
        try:
            os.kill(pid, 9)
        except Exception:
            pass


async def _check_session() -> tuple[bool, str]:
    """Actually open Onshape. Counting cookies proves nothing: Onshape's
    session cookies carry no expiry and are revoked server-side, so a
    dead session looks identical to a live one on disk.
    """
    from .driver import OnshapeDriver

    d = OnshapeDriver()
    try:
        await d.start(headless=settings.headless)
        await d.open()
        url = d.page.url
        has_tools = await d.page.locator("[command-id='newSketch']").count()
        if "signin" in url:
            return False, "Onshape redirected to signin"
        if not has_tools:
            return False, f"opened {url[:60]} but found no Part Studio toolbar"
        return True, url
    finally:
        try:
            await d.close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(
        prog="onshape-mcp up",
        description="Preflight everything, then serve a connector URL.",
    )
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    ap.add_argument(
        "--skip-session-check",
        action="store_true",
        help="Skip opening Onshape (faster, but a dead session will only "
        "surface later as a tool error).",
    )
    args = ap.parse_args(argv if argv is not None else sys.argv[2:])

    print("onshape-mcp up")
    print("=" * 68)

    print("[1/4] Clearing stale processes")
    _clear_strays(args.port)
    if not _port_is_free("127.0.0.1", args.port):
        sys.exit(
            f"\nPort {args.port} is still busy after cleanup — something outside this\n"
            f"project is holding it. Free it, or run: onshape-mcp up --port {args.port + 1}"
        )
    _say(True, f"port {args.port} free")

    print("[2/4] Browser engine")
    if settings.cdp_url:
        _say(True, f"attaching to your Chrome at {settings.cdp_url} (no download needed)")
    else:
        from .setup import ensure_playwright_browsers

        ensure_playwright_browsers()

    print("[3/4] Onshape session")
    if args.skip_session_check:
        _say(None, "skipped")
    else:
        try:
            ok, detail = asyncio.run(_check_session())
        except Exception as e:
            ok, detail = False, f"{type(e).__name__}: {e}"
        if not ok:
            print()
            sys.exit(
                f"  ✗ Onshape session is not usable: {detail}\n\n"
                "Fix it with ONE of:\n"
                "  • Sign in to Onshape in your normal browser, then re-run this.\n"
                "    Your browser's live session is used before any saved file.\n"
                "  • onshape-mcp login   (opens a browser, waits for you, saves cookies)\n"
            )
        _say(True, f"signed in — {detail[:70]}")

    print("[4/4] Public URL")
    tunnel = find_tunnel_binary()
    if tunnel is None:
        _say(None, "no tunnel tool; serving locally only")
    elif _ngrok_domain():
        _say(True, f"ngrok reserved domain {_ngrok_domain()} — URL is permanent")
    elif _stable_subdomain():
        _say(None, f"localtunnel will REQUEST '{_stable_subdomain()}' (best effort, not guaranteed)")
    else:
        _say(None, "random hostname each run — set ONSHAPE_NGROK_DOMAIN for a permanent one")
    print("=" * 68)

    from .tunnel import run_tunnel_and_server

    run_tunnel_and_server(port=args.port)
