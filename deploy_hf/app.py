"""Hugging Face Space entrypoint for Onshape MCP.
Uses standard Gradio launch with FastMCP SSE routes injected at startup.
Provides:
1. Model Context Protocol Streamable HTTP endpoint at `/mcp`
3. Live interactive dashboard on Gradio
"""

from __future__ import annotations

import os
import sys

import enum
if not hasattr(enum, "StrEnum"):
    class StrEnum(str, enum.Enum):
        pass
    enum.StrEnum = StrEnum

import gradio as gr
import subprocess
from mcp.server.transport_security import TransportSecuritySettings

try:
    print("[startup] Checking Playwright Chromium...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("[startup] Playwright Chromium installed.")
except Exception as e:
    print(f"[startup] Playwright install note: {e}")

try:
    import spaces
except ImportError:
    class spaces:
        @staticmethod
        def GPU(fn=None, **kwargs):
            if fn:
                return fn
            return lambda f: f

from onshape_mcp.server import mcp

# Disable DNS rebinding check for cloud deployment so ChatGPT and external hosts can connect
mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)

# This Space drives a browser holding an Onshape session, on a public URL.
# Set MCP_TOKEN as a Space secret; clients append ?token=... to the SSE URL.
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
if not MCP_TOKEN:
    raise SystemExit(
        "MCP_TOKEN is not set. Add it under Settings > Variables and secrets\n"
        "before starting this Space — without it, anyone who finds the URL can\n"
        "edit the Onshape documents this Space is logged into."
    )


# ZeroGPU registered handler
@spaces.GPU
def check_status() -> str:
    return "✅ Onshape MCP Server is ACTIVE and ready to receive CAD commands from ChatGPT, Claude, and Cursor."


with gr.Blocks(title="Onshape CAD MCP Server") as demo:
    gr.Markdown("""
    # 📐 Onshape CAD MCP Server
    **Zero-Setup 3D CAD Modeling for AI Agents**

    This server connects **ChatGPT**, **Claude**, and **Cursor** to Onshape via the Model Context Protocol (MCP).

    ---

    ### 🔗 Connection Endpoint
    Paste this into ChatGPT's connector dialog, with your token appended:
    ```text
    https://x-r-1-8-onshape-cad-mcp.hf.space/mcp?token=YOUR_MCP_TOKEN
    ```
    The token is the `MCP_TOKEN` Space secret. It gates every request —
    this endpoint drives a live Onshape session.
    """)
    status_btn = gr.Button("Test Server Engine", variant="primary")
    status_out = gr.Textbox(label="Engine Status", interactive=False)
    status_btn.click(fn=check_status, outputs=status_out)

    gr.Markdown("""
    ### 🛠️ Available Features:
    * 35+ full CAD sketch tools (lines, arcs, splines, fillets, trims, mirrors, offsets, constraints)
    * Automated browser canvas automation
    * Zero token cost deterministic CAD execution
    """)


if __name__ == "__main__":
    from onshape_mcp.tunnel import require_token

    app, local_url, share_url = demo.launch(prevent_thread_lock=True, ssr_mode=False)
    # Streamable HTTP at /mcp, not SSE: proxies (Cloudflare, and HF's own
    # front end) buffer the long-lived SSE response, so the handshake
    # never completes through them.
    for route in mcp.streamable_http_app().routes:
        route.app = require_token(route.app, MCP_TOKEN)
        app.routes.insert(0, route)
    demo.block_thread()
