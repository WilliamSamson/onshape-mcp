# Architecture

## Components

| Module                       | Role                                                  | Local-only? |
|------------------------------|-------------------------------------------------------|-------------|
| `src/onshape_mcp/server.py`  | MCP server, tool surface                              | No          |
| `src/onshape_mcp/driver.py`  | Playwright + persistent Chromium profile              | Writes to `playwright-profile/` (gitignored) |
| `src/onshape_mcp/vision.py`  | Gemini web client (cookie-auth)                       | Reads `cookies/gemini.cookies.json` (gitignored) |
| `src/onshape_mcp/tools.py`   | Tool datasheet + prompt renderer                      | No          |
| `src/onshape_mcp/journal.py` | Append-only action log                                | Writes to `state/` (gitignored) |
| `src/onshape_mcp/config.py`  | `.env` loader, paths                                  | No (code) — values local |
| `scripts/m0_*.py`            | Milestone-0 sanity scripts                            | No          |

## Action loop (target)

1. User asks the LLM to "draw a 50×30mm bracket with a 5mm chamfer."
2. The LLM calls `mcp__onshape__describe_view()` to see the current state.
3. The LLM picks a `mcp__onshape__*` tool (e.g. `onshape_sketch_start`).
4. The MCP server records the call in the journal, executes the UI op via
   Playwright, returns success + a fresh screenshot.
5. Repeat until the goal is met or the model asks for clarification.

## Undo + replay

Because every action is journaled, we can:

- **Undo**: replay the journal in reverse on the local session, or
  just hit `Ctrl+Z` N times via `ui.undo`.
- **Replay**: rerun the journal against a fresh doc for regression.
- **Branch**: snapshot the journal, try an alternative, restore.

## Cost controls

- Cache the datasheet prompt block — same for every call within a session.
- Use a cheap model for "which tool next" decisions; escalate to vision only
  when the viewport state is ambiguous.
- Rate-limit vision calls (Gemini web has a soft per-hour cap even on Plus).
- Stuck detector: if 3 actions in a row don't change the screenshot, stop.

## Threat model

| Threat                              | Mitigation                                    |
|-------------------------------------|-----------------------------------------------|
| Cookie leak via git                 | `.gitignore` from day one + SECURITY.md       |
| Screenshot of private doc in logs   | gitignored + journal off by default in prod   |
| ToS violation via UI automation     | Document it; ship an opt-in disclaimer        |
| Gemini web rate limit               | Backoff + queue + local fallback model slot   |
