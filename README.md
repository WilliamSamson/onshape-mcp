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
- **M1** done: driver primitives, Onshape tool datasheet, 43 MCP tools across
  sketching, constraints, dimensions, features and feature-tree editing, plus
  the closed-loop `act(goal)` agent and a deterministic fast path that skips
  the LLM entirely for parseable goals.
- **M2** next: pattern, mirror_body, assembly.mate, sketch.constrain flyout,
  journal-replay undo, a real perceptual-diff for the stuck detector.

## A note on sizes

Sizes come from Onshape's dimension solver, not from pixel measurements.
Tools draw a rough shape at a scale derived from the live canvas, then drive
the true millimetre value in — so a rectangle or circle is exactly the size
you asked for regardless of zoom. All dimension arguments are millimetres
unless you write a unit (`"10 cm"`, `"2 in"`); bare numbers are never
reinterpreted. Polygon radius is currently drawn-to-scale but not
solver-driven; see the `ponytail:` note in `ui_actions.py`.

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

## Install

Add this to your MCP client's config. Nothing else — no account, no API key,
no per-user server, no token.

```json
{
  "mcpServers": {
    "onshape": {
      "command": "uvx",
      "args": ["onshape-mcp"]
    }
  }
}
```

| Client | File |
| --- | --- |
| Claude Desktop | `claude_desktop_config.json` |
| Claude Code | `claude mcp add onshape -- uvx onshape-mcp` |
| Cursor | `~/.cursor/mcp.json` |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` |
| VS Code (Cline / Roo) | `cline_mcp_settings.json` |

Or let it find and write those for you:

```bash
uvx onshape-mcp setup -y
```

Restart the client and ask for something:

> *Draw a 50 x 30 mm rectangle on the Top plane*

### Why there is nothing to configure

**Your Onshape session is read from the browser you already use.** If you are
signed in to Onshape in Chrome, Brave, Edge, Firefox or Vivaldi, the server
picks that session up. Nothing to export, no keys to paste, and no per-user
server to stand up. Signed out? Run `onshape-mcp login` once.

Chromium is downloaded on first use (~150 MB). `setup` does it up front so the
first request is not waiting on a download.

Optional `.env` settings: `ONSHAPE_DEFAULT_DOC` to pin a document,
`ONSHAPE_HEADLESS=false` to watch it work, `ONSHAPE_CDP_URL` to drive a Chrome
you already have open.

## Remote clients (ChatGPT web)

The config above covers every client that speaks MCP over stdio. ChatGPT on the
web needs an HTTPS endpoint instead, which is what `up` provides.

## One command: `up`

```bash
uv run onshape-mcp up
```

That is the whole setup. It stops stale servers and orphaned tunnels (an
abandoned tunnel keeps a public hostname alive with nothing behind it, which
is what a 502 in your client actually means), frees the port, checks the
browser engine, **opens Onshape and confirms you are signed in**, then serves
and prints the connector URL.

It refuses to print a URL it has not proven works. Counting cookies is not a
check: Onshape's session cookies carry no expiry and are revoked server-side,
so a dead session looks identical to a live one on disk.

Paste the printed URL into ChatGPT under **Settings → Connectors → Add**. It
drives the browser on *your* machine with *your* Onshape session.

### Make the URL permanent

By default the hostname is random each run, so you must re-paste it after every
restart. To stop that, reserve an ngrok domain (free tier includes one) and set:

```bash
ONSHAPE_NGROK_DOMAIN=your-name.ngrok-free.app
```

`up` then uses it and the URL is identical every run — paste it into ChatGPT
once. `ONSHAPE_TUNNEL_SUBDOMAIN` asks localtunnel for a name instead, but that
is best-effort: it silently hands back a random hostname when the name is
taken, so the banner tells you whether you actually got what you asked for.

With a permanent URL the server can update itself in place:

- `onshape_mcp_version` — the running commit, and whether `origin/main` moved.
- `onshape_mcp_update(restart=True)` — pull and re-exec. The URL survives, so
  the connector just reconnects.

**The URL is a credential.** Anyone holding it can edit your Onshape documents.
Pin `MCP_TOKEN` in `.env` to keep the token stable across restarts.

The Space (`deploy_hf/`) installs this package from git rather than vendoring a
copy of `src/`, serves the same `/mcp` endpoint, and requires its own
`MCP_TOKEN` secret before it will start.

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

## Interactive sketch editing

A new one-step controller supports shared browser sessions, inline frames,
confirmed target previews, detail edits, manual handoff, request retry protection,
and checkpoint-checked sketch undo. See [the interactive guide](docs/interactive-sketch.md)
for setup, tool calls, verification semantics and remaining live acceptance checks.
