---
title: Onshape CAD MCP
emoji: 📐
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 5.20.0
app_file: app.py
pinned: false
---

# 📐 Onshape CAD MCP Server

A natural-language agent that models 3D CAD directly in Onshape. Drives the Onshape web canvas using Playwright and Model Context Protocol.

### 🔗 Connect to ChatGPT / Claude / Cursor

**MCP SSE Endpoint:**
```text
https://x-r-1-8-onshape-cad-mcp.hf.space/sse
```

### Features
* **Zero Installation for Testers**: Connect directly over SSE without running local code.
* **Full Sketch Suite**: 35+ tools (lines, rectangles, splines, polygons, fillets, chamfers, offset, trim, mirror).
* **Deterministic Fast Engine**: 0-token instant CAD operations without LLM overhead.
