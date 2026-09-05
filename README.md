# onshape-mcp

I wanted a way to drive Onshape from a language model the way I drive it with
my hands. Click a face. Draw a sketch. Extrude. Chamfer. The existing Onshape
MCP wraps the REST API and FeatureScript, which works but feels like coding,
not modeling. This server aims at the other 70% of CAD work that lives in
the viewport.

It uses a vision-capable LLM (Gemini web, no API key, my Plus cookies) as
eyes, Playwright as hands, and an MCP surface so any MCP-aware client can
talk to it. Every action is journaled, so I can undo, replay, or branch.

## Status

- **M0** done: scaffold, smoke tests, public repo, safety rails.
- **M1** done: driver primitives, Onshape tool datasheet, 10 wired tools
  (`view.fit`, `sketch.start/rectangle/circle/line/exit`, `feature.extrude/fillet/chamfer`,
  `select.face/edge`, `ui.undo/redo`), closed-loop `act(goal)` agent.
- **M2** next: pattern, mirror_body, assembly.mate, sketch.constrain flyout,
  journal-replay undo, a real perceptual-diff for the stuck detector.

## What it looks like from the client side

Two ways to drive it:

**Direct tools.** I call individual MCP tools when I want fine control:
`screenshot`, `describe_view`, `viewport_size`, `journal_tail`, `tool_datasheet`,
`open_doc`, and the per-tool `onshape_*` ones. Useful when I want to see
each step and steer.

**Closed-loop `act`.** I just say what I want:
`act(goal="draw a 50x30mm rectangle on the top plane and extrude it 10mm")`.
Gemini sees each screenshot, picks the next tool, calls it, repeats until
the goal is met or it bails. Bounded by `max_steps` (default 25) and a
stuck detector (3 identical screenshots in a row = stop).

## Quick Start for Testers (1-Command Smart Setup)

To test Onshape MCP in **Claude Desktop** with zero manual configuration:

```bash
uvx --from git+https://github.com/WilliamSamson/onshape-mcp onshape-mcp setup
```

The smart wizard will automatically:
1. Ensure Playwright's Chromium browser engine is downloaded.
2. Auto-detect and sync your active Onshape login session from your local browser (Chrome, Edge, Brave, etc.) into `~/.onshape-mcp/cookies/` — no manual cookie copying needed.
3. Auto-configure Claude Desktop (`claude_desktop_config.json`) across macOS, Windows, and Linux.
4. Keep all credentials and cookies isolated on your machine with **zero hardcoded paths**.

Restart Claude Desktop, and you can immediately ask:
> *"Draw a 10cm by 5cm box on the Top plane in Onshape"*

---

## Local Development & Manual Run

```bash
# Clone and install
git clone https://github.com/WilliamSamson/onshape-mcp.git
cd onshape-mcp
uv sync

# Run the smart setup or start server
uv run onshape-mcp setup
uv run onshape-mcp
```

## A note on Google + automated browsers

Google blocks automated browser logins ("This browser or app may not be
secure") when you launch Playwright's bundled Chromium against a Google
login page. I hit this. The fix in `bootstrap.py` is to try reading the
Gemini cookies straight out of my real Chrome session first, via
`browser-cookie3`. No browser launch, no automation block. If that
somehow fails (Chrome locked, no Chrome installed), it falls back to
launching real Chrome via Playwright (`channel="chrome"`), and only as
a last resort launches bundled Chromium.

The same Chrome-first choice applies to the main driver. Set
`ONSHAPE_BROWSER_CHANNEL=auto` (the default) and the server uses real
Chrome when available, falling back to bundled Chromium. Set it to
`chromium` to skip the Chrome attempt (e.g. on a Pi with no Chrome
installed).

## Architecture in one screen

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
                └────────────────┘
```

Five layers, bottom up:

1. **Driver primitives** in `driver.py`. Click, type, press chord, drag,
   find by text, screenshot. Knows nothing about Onshape.
2. **UI bindings** in `shortcuts.py`. Maps each semantic tool to its
   keyboard chord or toolbar button, with a `confidence` flag so I know
   what to retest.
3. **UI actions** in `ui_actions.py`. Compose primitives + bindings into
   one logical op (`sketch_rectangle(d, c1, c2)` = activate tool, click
   c1, click c2, Esc, screenshot). Every op journals itself.
4. **Dispatch table** in `server.py`. Maps tool names back to ui_actions
   functions, flattens LLM-friendly args to tuples.
5. **Agent loop** `act(goal)` in `server.py`. Screenshot, ask Gemini
   what's next, dispatch, repeat. Bounded by `max_steps` and a stuck
   detector.

## License

MIT. See [LICENSE](LICENSE).
