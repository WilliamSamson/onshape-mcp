"""Automatic web tunnel manager for Onshape MCP.
Spawns the local SSE server and exposes a secure public HTTPS endpoint
(via Cloudflare Quick Tunnels or Localtunnel) with zero configuration.

Allows web AIs (ChatGPT Web, LibreChat, Open WebUI) to connect instantly.
"""

from __future__ import annotations

import re
import secrets
import shutil
import subprocess
import threading
import time
from typing import Any

from .config import settings


def require_token(app: Any, token: str) -> Any:
    """Wrap an ASGI app so every request must present `token`.

    This server drives a browser logged into the user's Onshape account,
    so an open endpoint is an account takeover. Clients send
    `Authorization: Bearer <token>` or `?token=<token>` — ChatGPT
    connectors only take a URL, hence the query form.

    Pure ASGI, not BaseHTTPMiddleware: the latter buffers responses and
    would stall the SSE stream this whole transport depends on.
    """
    from urllib.parse import parse_qs

    async def gated(scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return await app(scope, receive, send)
        supplied = ""
        for key, value in scope.get("headers", []):
            if key == b"authorization":
                header = value.decode("latin-1")
                if header.lower().startswith("bearer "):
                    supplied = header[7:]
                break
        if not supplied:
            qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
            supplied = (qs.get("token") or [""])[0]
        if not secrets.compare_digest(supplied, token):
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
            return
        await app(scope, receive, send)

    return gated


def serve_sse(host: str, port: int, token: str) -> None:
    """Run the MCP SSE app behind a shared-secret check."""
    import uvicorn

    from .server import mcp

    uvicorn.run(require_token(mcp.sse_app(), token), host=host, port=port, log_level="info")


def find_tunnel_binary() -> tuple[str, list[str]] | None:
    """Find available tunnel tool (cloudflared or localtunnel)."""
    # 1. Cloudflare tunnel (no sign-up, fast, reliable)
    cf = shutil.which("cloudflared")
    if cf:
        return ("cloudflared", [cf, "tunnel", "--url"])

    # 2. Localtunnel via npx
    npx = shutil.which("npx")
    if npx:
        return ("localtunnel", [npx, "-y", "localtunnel", "--port"])

    return None


def run_tunnel_and_server(port: int = 8000, host: str = "127.0.0.1") -> None:
    """Start the MCP SSE server and attach an auto-tunnel for web AIs."""
    # A tunnel puts this on the public internet. An unguessable URL is not
    # authentication, so mint a token if the user hasn't set one.
    token = settings.mcp_token or secrets.token_urlsafe(24)
    # Only the tunnel process needs to reach the server; binding the
    # loopback keeps it off the LAN as well.
    host = "127.0.0.1"

    tunnel_info = find_tunnel_binary()
    if not tunnel_info:
        print("=" * 68)
        print("⚠ No tunneling tool (cloudflared or npx) found on your system.")
        print("To enable instant web sharing, install cloudflared:")
        print("  • Mac:     brew install cloudflared")
        print("  • Linux:   sudo apt install cloudflared  (or download binary)")
        print("  • Windows: winget install Cloudflare.cloudflared")
        print("=" * 68)
        print(f"Starting local SSE server at http://{host}:{port}/sse?token={token}")
        serve_sse(host, port, token)
        return

    tunnel_type, tunnel_cmd = tunnel_info
    local_url = f"http://{host}:{port}"

    print("=" * 68)
    print("   🌐 Onshape MCP — Instant Web Sharing & ChatGPT Connector")
    print("=" * 68)
    print(f"Starting local SSE engine on port {port}...")

    # Start the tunnel process in the background
    if tunnel_type == "cloudflared":
        cmd = [*tunnel_cmd, local_url]
    else:
        cmd = [*tunnel_cmd, str(port)]

    tunnel_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    public_url: str | None = None
    start_time = time.time()

    # Read output to capture the public URL
    def _read_stream(stream: Any) -> None:
        nonlocal public_url
        if not stream:
            return
        for line in iter(stream.readline, ""):
            if not line:
                break
            # Cloudflare pattern
            m_cf = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if m_cf:
                public_url = m_cf.group(0)
                break
            # Localtunnel pattern
            m_lt = re.search(r"https://[a-zA-Z0-9-]+\.loca\.lt", line)
            if m_lt:
                public_url = m_lt.group(0)
                break

    t_err = threading.Thread(target=_read_stream, args=(tunnel_proc.stderr,), daemon=True)
    t_out = threading.Thread(target=_read_stream, args=(tunnel_proc.stdout,), daemon=True)
    t_err.start()
    t_out.start()

    print("Requesting secure HTTPS tunnel from Cloudflare...")
    while public_url is None and (time.time() - start_time < 15):
        time.sleep(0.5)

    if public_url:
        sse_url = f"{public_url.rstrip('/')}/sse?token={token}"
        print("\n" + "=" * 68)
        print("🎉 Your Onshape MCP is live on the internet:")
        print(f"\n👉 MCP SSE URL:  \033[1;32m{sse_url}\033[0m\n")
        print("This URL drives YOUR logged-in Onshape session. Treat it as a")
        print("password: anyone who has it can edit your documents. It dies")
        print("when you Ctrl+C, and a new token is minted each run unless you")
        print("pin one with MCP_TOKEN in .env.\n")
        print("1. ChatGPT: Settings > Connectors > Add, paste the full URL.")
        print("2. LibreChat / Open WebUI: add it under MCP servers.")
        print("=" * 68 + "\n")
    else:
        print("⚠ Tunnel did not return a public URL in 15s. Running locally.")
        print(f"Local endpoint: http://{host}:{port}/sse?token={token}\n")

    try:
        serve_sse(host, port, token)
    finally:
        tunnel_proc.terminate()
        tunnel_proc.wait()
