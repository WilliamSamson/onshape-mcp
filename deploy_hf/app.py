"""Hugging Face Space entrypoint for Onshape MCP.
Uses standard Gradio launch with FastMCP SSE routes injected at startup.
Provides:
1. Model Context Protocol SSE stream at `/sse` for ChatGPT, Claude, and Cursor
2. FastMCP message receiver at `/messages/`
3. Live interactive dashboard on Gradio
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import enum
if not hasattr(enum, "StrEnum"):
    class StrEnum(str, enum.Enum):
        pass
    enum.StrEnum = StrEnum

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent / "src"))

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
    Copy this SSE endpoint into ChatGPT's **New Plugin / Server URL** dialog:
    ```text
    https://x-r-1-8-onshape-cad-mcp.hf.space/sse
    ```
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
    app, local_url, share_url = demo.launch(prevent_thread_lock=True, ssr_mode=False)
    sse_app = mcp.sse_app()
    for route in sse_app.routes:
        app.routes.insert(0, route)
    demo.block_thread()
