# Architecture

## Components

| Module                          | Role                                                       | Local-only? |
|---------------------------------|------------------------------------------------------------|-------------|
| `src/onshape_mcp/server.py`     | MCP server, tool surface, dispatch table, `act()` loop     | No          |
| `src/onshape_mcp/driver.py`     | Playwright + persistent Chromium + UI primitives           | Writes to `playwright-profile/` (gitignored) |
| `src/onshape_mcp/ui_actions.py` | High-level Onshape ops (sketch, extrude, fillet, …)        | No          |
| `src/onshape_mcp/shortcuts.py`  | Keyboard + toolbar bindings, with confidence flags        | No          |
| `src/onshape_mcp/vision.py`     | Gemini web client (cookie-auth)                            | Reads `cookies/gemini.cookies.json` (gitignored) |
| `src/onshape_mcp/tools.py`      | Tool datasheet + prompt renderer                           | No          |
| `src/onshape_mcp/journal.py`    | Append-only action log                                     | Writes to `state/` (gitignored) |
| `src/onshape_mcp/config.py`     | `.env` loader, paths                                       | No (code) — values local |
| `scripts/m0_*.py`               | Milestone-0 sanity scripts                                 | No          |

## Layers (bottom-up)

1. **Driver primitives** — `click`, `type_text`, `press_chord`, `drag`,
   `find_by_text`, `screenshot`, `screenshot_clip`. Knows nothing about
   Onshape; just the browser.
2. **UI bindings** — `shortcuts.py`. Maps semantic tool names to keyboard
   chords or toolbar button text. Each binding has a confidence flag.
3. **UI actions** — `ui_actions.py`. Compose primitives + bindings into
   one logical op (e.g. `sketch_rectangle(d, c1, c2)` = activate tool,
   click c1, click c2, Esc, screenshot). Every op records to the journal.
4. **Dispatch table** — `server.py:TOOL_DISPATCH`. Maps tool names back
   to `ui_actions` functions, flattens LLM-friendly args to tuples.
5. **Agent loop** — `act(goal)` in `server.py`. Screenshot → ask Gemini
   "what's the next tool?" → dispatch → repeat. Bounded by `max_steps`
   and a stuck detector (no screenshot change for 3 turns).

## Action loop

1. User asks the LLM to "draw a 50×30mm bracket with a 5mm chamfer."
2. The LLM calls `act(goal=...)` (or chains `screenshot` / `describe_view`
   itself).
3. `act()` takes a screenshot, asks Gemini for a JSON `{tool, args} | {done}`.
4. Dispatch table routes the tool call to `ui_actions`. Result + screenshot
   are journaled.
5. Repeat until `done` is true, `max_steps` reached, or the stuck detector fires.

## Undo + replay

Because every action is journaled, we can:

- **Undo**: replay the journal in reverse on the local session, or just
  hit `Ctrl+Z` N times via `ui.undo`.
- **Replay**: rerun the journal against a fresh doc for regression.
- **Branch**: snapshot the journal, try an alternative, restore.

## Cost controls

- Cache the datasheet prompt block — same for every call within a session.
- Use a cheap model for "which tool next" decisions; escalate to vision
  only when the viewport state is ambiguous.
- Rate-limit vision calls (Gemini web has a soft per-hour cap even on Plus).
- Stuck detector: if 3 actions in a row don't change the screenshot, stop.

## Status (M1)

- ✅ Driver primitives complete
- ✅ First 10 datasheet tools wired against real Playwright clicks
- ✅ `act(goal)` closed-loop agent + stuck detector
- ✅ Unit tests passing
- 🚧 Gemini web 2.x client — needs verification on first install
- 🚧 M2: pattern, mirror_body, assembly.mate, advanced selection
- 🚧 M2: undo-by-journal-replay (currently Ctrl+Z only)

## Threat model

| Threat                              | Mitigation                                    |
|-------------------------------------|-----------------------------------------------|
| Cookie leak via git                 | `.gitignore` from day one + SECURITY.md       |
| Screenshot of private doc in logs   | gitignored + journal off by default in prod   |
| ToS violation via UI automation     | Document it; ship an opt-in disclaimer        |
| Gemini web rate limit               | Backoff + queue + local fallback model slot   |
| Onshape UI changes break bindings   | All bindings in `shortcuts.py` w/ confidence flags |
