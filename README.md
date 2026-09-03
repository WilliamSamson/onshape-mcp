# onshape-mcp

A visual, agentic MCP server for **Onshape**. You give it a goal in natural
language, it drives the Onshape web UI the way a human would — clicking faces,
drawing sketches, extruding, chamfering — using a vision-capable LLM
(Gemini web) for eyes and reasoning, and Playwright for hands.

No FeatureScript black box. Every action is logged and reversible. Every pick
is a real click on a real face. Undo works because we journaled every step.

## Why

The existing Onshape MCP wraps the REST API + FeatureScript. That's reliable
but feels like coding, not modeling. This server aims for the other 70% of
CAD work that lives in the viewport: pick a face, drag a dimension, mirror a
feature, mate this to that.

## Architecture (one screen)

```
                ┌────────────────────────────────────────┐
                │  MCP client (Claude Code, Cursor, …)  │
                └──────────────────┬─────────────────────┘
                                   │ mcp__onshape__* tool calls
                ┌──────────────────▼─────────────────────┐
                │  onshape-mcp server (this repo)        │
                │  ┌──────────┐  ┌──────────┐  ┌──────┐  │
                │  │  tools   │  │ journal  │  │ loop │  │
                │  └────┬─────┘  └────┬─────┘  └───┬──┘  │
                └───────┼─────────────┼────────────┼─────┘
                        │             │            │
        ┌───────────────▼─────┐  ┌────▼─────┐  ┌───▼────────────┐
        │  Playwright driver  │  │  JSONL   │  │  Gemini web    │
        │  (headless Chromium)│  │  state/  │  │  (vision + LLM)│
        └───────────────┬─────┘  └──────────┘  └────────────────┘
                        │
                ┌───────▼────────┐
                │  Onshape web   │
                │  (cad.onshape.com) │
                └────────────────┘
```

## Status

🚧 **Milestone 0** — scaffolding, login test, Gemini web test.
Targets for the first working prototype: draw a sketch, extrude it, add a
chamfer, save the doc.

## Quick start

```bash
git clone https://github.com/WilliamSamson/onshape-mcp
cd onshape-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Gemini cookie path, etc.

# 1. Log into Onshape once (saves session to playwright-profile/)
python -m onshape_mcp.driver login

# 2. Verify Gemini web works with your cookies
python scripts/m0_gemini.py

# 3. Run the MCP server
python -m onshape_mcp.server
```

Then point your MCP client at it.

## Safety

Public repo — see [SECURITY.md](SECURITY.md). No credentials, cookies, logs,
or screenshots of your documents are ever committed. All sensitive paths are
gitignored from day one.

## License

MIT — see [LICENSE](LICENSE).
