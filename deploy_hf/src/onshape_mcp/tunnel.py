"""Automatic web tunnel manager for Onshape MCP.
Spawns the local SSE server and exposes a secure public HTTPS endpoint
(via Cloudflare Quick Tunnels or Localtunnel) with zero configuration.

Allows web AIs (ChatGPT Web, LibreChat, Open WebUI) to connect instantly.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

from .config import settings


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
    """Start the FastMCP SSE server and attach an auto-tunnel for web AIs."""
    tunnel_info = find_tunnel_binary()
    if not tunnel_info:
        print("=" * 68)
        print("⚠ No tunneling tool (cloudflared or npx) found on your system.")
        print("To enable instant web sharing, install cloudflared:")
        print("  • Mac:     brew install cloudflared")
        print("  • Linux:   sudo apt install cloudflared  (or download binary)")
        print("  • Windows: winget install Cloudflare.cloudflared")
        print("=" * 68)
        # Fallback to local SSE only
        from .server import mcp
        mcp.settings.host = host
        mcp.settings.port = port
        print(f"Starting local SSE server at http://{host}:{port}/sse ...")
        mcp.run(transport="sse")
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
        sse_url = f"{public_url.rstrip('/')}/sse"
        print("\n" + "=" * 68)
        print("🎉 SUCCESS! Your Onshape MCP is live on the internet:")
        print(f"\n👉 MCP SSE URL:  \033[1;32m{sse_url}\033[0m\n")
        print("How to use this link:")
        print("1. In ChatGPT Web: Add this link to your MCP / Custom GPT connector.")
        print("2. In LibreChat / Open WebUI: Add this link under MCP servers.")
        print("3. Press Ctrl+C in this terminal when you want to disconnect.")
        print("=" * 68 + "\n")
    else:
        print("⚠ Tunnel did not return a public URL in 15s. Running locally.")
        print(f"Local endpoint: http://{host}:{port}/sse\n")

    # Now run the SSE server in the main thread
    from .server import mcp
    mcp.settings.host = host
    mcp.settings.port = port

    try:
        mcp.run(transport="sse")
    finally:
        tunnel_proc.terminate()
        tunnel_proc.wait()
