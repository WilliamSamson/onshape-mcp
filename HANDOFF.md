# Handoff

This is the state of `onshape-mcp` as of M1 done. Written so a fresh
agent (or me, six months from now) can pick up without re-deriving
anything.

## What this is

A visual agentic MCP server for Onshape. Drives the Onshape web UI
like a human would (click face, draw sketch, extrude, chamfer). Uses
Gemini web for vision + reasoning, Playwright for hands.

Stack: Python 3.11+, FastMCP, Playwright, Gemini web cookies, no API
bills. Public repo: `WilliamSamson/onshape-mcp` (MIT).

## Repo layout

```
src/onshape_mcp/
  server.py         MCP tool surface + dispatch table + act(goal) loop
  driver.py         Playwright + Chrome first, Chromium fallback, WebGL args
  ui_actions.py     14 high-level Onshape ops (sketch, extrude, fillet, ...)
  shortcuts.py      Keyboard + toolbar bindings, with confidence flags
  vision.py         Gemini web client (cookie-auth, no API key)
  tools.py          Tool datasheet + prompt renderer
  journal.py        Append-only JSONL action log
  config.py         .env loader, repo-root detection

scripts/
  bootstrap.py              One-shot setup (idempotent, re-execs into venv)
  extract_gemini_cookies.py Headed Playwright, fall back path
  extract_cookies_from_chrome.py  Reads cookies from real Chrome via browser-cookie3
  serve.sh                  One-command server start (this is what you run)
  m0_login.py               Sanity: open Onshape, verify logged in
  m0_gemini.py              Sanity: send image to Gemini, get description

docs/
  architecture.md   What each file does, why this stack
  datasheet.md      Tool reference (mirror of tools.py)
```

## What's done (M0 + M1)

- venv, deps, Chromium, cookies, login all automated via `bootstrap.py`
- 14 tools wired against real Playwright clicks: `view.fit/top`,
  `sketch.start/rectangle/circle/line/exit`, `feature.extrude/fillet/chamfer`,
  `select.face/edge`, `ui.undo/redo`
- Closed-loop `act(goal=...)` with max-steps cap and stuck detector
- Cookie handling: plain JSON, not Chrome's encrypted DB (keyring issue
  workaround, see below)
- 11 smoke tests passing

## Critical lessons (do not relearn these)

### 1. Chrome's Linux cookie DB is encrypted with a keyring key

The keyring is only available to graphical sessions. Headless Playwright
cannot decrypt the cookies, so even after a successful headed login,
the headless run looks anonymous and Onshape redirects to /signin.

**Fix**: store cookies as plain JSON in `cookies/onshape.cookies.json`.
Login dumps via `context.cookies()`, headless re-injects via
`context.add_cookies()`. Same pattern for Gemini (different cookies,
same keyring-free JSON file).

### 2. Don't compute repo root from `__file__`

If the package is installed (which `pip install .` does), `__file__`
points at `.venv/lib/python3.14/site-packages/onshape_mcp/config.py`,
not the source. All relative paths end up inside the venv.

**Fix**: walk up from `Path.cwd()` looking for `pyproject.toml`. See
`config.py:_find_repo_root`.

### 3. Google blocks Playwright's bundled Chromium from logging in

"This browser or app may not be secure." Server-side detection, not
fixable with flags.

**Fix**: read cookies from the user's real Chrome via `browser-cookie3`.
No browser launch, no block. Fall back to Playwright with
`channel="chrome"` if that fails.

### 4. WebGL needs explicit flags in headless mode

Onshape renders with WebGL. In headless Chrome, the canvas stays blank
without these args:
```
--use-gl=swiftshader --enable-webgl --ignore-gpu-blocklist
```

### 5. Use `networkidle` not `domcontentloaded` for SPAs

Onshape is a SPA. `domcontentloaded` fires before the canvas renders.
Use `wait_until="networkidle"` and a `wait_for_app()` that checks for
the toolbar buttons.

## How to run (current state)

```bash
cd ~/Codes/onshape-mcp
./scripts/serve.sh             # foreground
./scripts/serve.sh --background # log to logs/serve.log
```

The MCP server speaks stdio JSON-RPC. Point any MCP client at it.

## Known issues / open work (M2 candidates)

- **Perceptual diff for stuck detector.** Current stuck check is a 4KB
  hash; misses "agent did 3 things that all produced tiny visual changes."
  Use `imagehash` or a small MobileNet embedding.
- **Journal-replay undo.** Journal is already there; need a
  `journal_undo(steps=N)` MCP tool that replays the reverse.
- **`sketch.constrain` flyout.** Toolbar has ~10 sub-buttons (Coincident,
  Horizontal, Vertical, Equal, Tangent). LLM needs to pick one. Refactor
  the binding to accept a constraint type.
- **`assembly.mate`.** Mate dialog has its own UX (mate type dropdown,
  multi-select). Lands after part-studio features are solid.
- **Pi deployment.** Set `ONSHAPE_BROWSER_CHANNEL=chromium` on the Pi
  (no Chrome). Headless Chromium works on ARM.
- **Gemini web 2.x API verification.** `gemini-webapi` jumped 0.x→2.x
  and the API surface in `vision.py` may have shifted. First install
  will tell us; pin and verify.

## Style notes (for whoever picks this up)

- First-person docs, no em-dash filler, no AI pleasantries
- Comments are technical, terse
- Decorative section dividers (`# ─── ...`) are fine for navigation
- `confidence: high/medium/low` on every UI binding; `planned/stub/working`
  on every tool
- All sensitive paths gitignored from day one
- No em-dashes in source or docs (one exception: a real warning in
  requirements.txt about a breaking version jump)
