# Architecture

Notes for me, six months from now, when I forget why I built it this way.

## What each file does

| File | Role |
|------|------|
| `src/onshape_mcp/server.py` | MCP server. Tool surface, dispatch table, `act()` loop. |
| `src/onshape_mcp/driver.py` | Playwright + persistent Chromium. UI primitives. Writes to `playwright-profile/` (gitignored). |
| `src/onshape_mcp/ui_actions.py` | High-level Onshape ops. sketch, extrude, fillet, etc. |
| `src/onshape_mcp/shortcuts.py` | Keyboard + toolbar bindings, with confidence flags. |
| `src/onshape_mcp/vision.py` | Gemini web client. Cookie-auth. Reads `cookies/gemini.cookies.json` (gitignored). |
| `src/onshape_mcp/tools.py` | Tool datasheet + prompt renderer. The vocabulary the LLM sees. |
| `src/onshape_mcp/journal.py` | Append-only action log. Writes to `state/` (gitignored). |
| `src/onshape_mcp/config.py` | `.env` loader, paths. |
| `scripts/bootstrap.py` | One-shot setup: venv, deps, Chromium, cookies, login, sanity checks. |
| `scripts/extract_gemini_cookies.py` | Headed Chromium, log in, dump Gemini cookies. |
| `scripts/m0_login.py`, `m0_gemini.py` | M0 sanity checks. Called by bootstrap. |

## The five layers

```
driver primitives  ->  UI bindings  ->  UI actions  ->  dispatch  ->  agent loop
   (browser)        (shortcuts.py)   (ui_actions)   (server.py)    (act())
```

I keep these in separate files because the failure modes differ. The bottom
layer is "is Playwright even working." The top layer is "did Gemini make a
sensible plan." Mixing them makes both harder to debug.

## Why I picked this stack

- **Playwright** because Onshape is browser-only. No desktop hooks, no UI
  automation API. Whatever I do, I'm driving a Chromium tab.
- **Persistent profile** so I log into Onshape once, and every subsequent
  run starts logged in. The profile dir is gitignored.
- **Gemini web** because I have a Plus subscription. I get a strong
  multimodal model, no API bill, and the cookie-auth path is well-trodden
  (reverse-engineered `gemini-webapi` package).
- **MCP** because I want this to plug into Claude Code, Cursor, and anything
  else that speaks MCP. The cost is one extra layer (the dispatch table)
  but the upside is it's not coupled to one client.
- **JSONL journal** because I want undo, replay, and the ability to
  diff a "what the agent did" session against my own.

## Cost controls

The closed loop is the expensive part. Each step is a screenshot upload +
a Gemini call. I've built in three brakes:

1. **Hard cap.** `max_steps` defaults to 25. An agent that takes 25 UI
   steps to draw a rectangle has gone off the rails.
2. **Stuck detector.** 3 screenshots in a row that look identical = stop.
   The current check is a 4KB hash, which catches "the agent clicked the
   same nothing 3 times" but not "3 tiny visual changes." M2 will switch
   to a perceptual hash.
3. **Cached datasheet.** The system prompt for `act()` is the same for
   every step in a session. I render it once.

## What I'd do differently

If I were starting over I'd probably:

- Skip the `act()` tool at first and just expose the primitives. The
  closed loop is fun to demo, but in practice I want to drive each step
  myself until the bindings are trustworthy.
- Use a real vision model only when the screenshot is ambiguous. Most
  steps, the LLM can pick the next tool from the journal + datasheet
  alone, no vision needed.
- Move the dispatch table to YAML so non-Python people can edit it.

## Open questions (M2 candidates)

- Real perceptual diff for the stuck detector. `imagehash` or a tiny
  MobileNet embedding both work.
- Journal-replay undo. The journal is already there; I just need a
  `journal_undo(steps=N)` MCP tool that replays the reverse.
- Constraint flyout (`sketch.constrain`). The toolbar has ~10 buttons
  (Coincident, Horizontal, Vertical, Equal, Tangent, …) and the LLM
  needs to pick the right one. Will probably want a sub-tool argument.
- Assembly.mate. The mate dialog is a separate beast (mate type
  dropdown, multiple selections). Will land after the part-studio
  features are solid.
- Vision feedback loop. Currently the agent just does step → screenshot
  → next. I'd like a "is this what you wanted?" prompt between
  high-impact steps (extrude, fillet) so it can course-correct.
