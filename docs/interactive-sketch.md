# Conversational, visible sketch editing

## Implemented workflow

This is a UI-driven controller, not FeatureScript generation. Drawing, editing,
zooming and undo use the browser UI. Feature API **GETs only** provide a persisted
entity/constraint inventory and dimension evidence. The existing M4 API writer
remains a separate legacy tool and is rejected inside interactive workflows.

1. **Shared visible session:** all server tools and the vision loop borrow one
   driver. Set `ONSHAPE_HEADLESS=false` to show a locally launched window, or use
   the existing `ONSHAPE_CDP_URL` attachment. With several document tabs, set
   `ONSHAPE_TAB_URL` to one exact URL. The first unrelated tab is never selected
   or navigated. Browser attachment does not close user-owned contexts.
2. **Point-and-talk:** `onshape_frame` returns an inline image and `frame_id`.
   `onshape_select_target` creates a named marker and returns its preview image
   and handle. The client asks the user to confirm the marker. Handles are
   screen-bound and invalidated after edits, zoom/view changes or manual handoff.
   Stable feature/entity IDs can be attached from the inventory; a coordinate
   marker alone is not proof that the intended CAD entity was selected.
3. **Detail editing:** queue `selection.edit` for an existing dimension label,
   a new edge dimension, point/control-point dragging, deleting an entity or
   constraint, construction toggling, trimming, extending, splitting, or adding
   a constraint across selected handles. Constraint-aware dragging is performed
   by Onshape's native solver; the controller does not invent geometry IDs.
4. **Precision:** `onshape_verify_dimension` checks an exact feature/constraint
   ID, literal unit expression, tolerance, and persisted `OK` feature state.
   Unknown expressions, missing IDs and uncommitted edits remain unverified.
   Interactive rectangles/circles are deliberately drawn rough without hidden
   dimension passes. Observe, select, dimension one edge, then observe/reselect
   the next edge. `view.zoom` scrolls the actual canvas around a pixel anchor.
   An applied edit is **not** automatically a verified correct model.
5. **Pause/resume:** `next` executes one semantic step and returns JSON + image.
   `pause` takes effect at the action boundary. `revise` replaces pending steps.
   `handoff` allows manual edits; `resume` refreshes state and expires selections.
   Legacy mutating tools are blocked while an interactive request owns the canvas.
6. **History:** unique screenshots and JSONL events preserve each observed state.
   A stable request ID prevents duplicate execution, including after restart.
   `restore` pauses an interrupted request and skips its uncertain attempted
   action; inspect the model and explicitly revise rather than replay blindly.
   `cancel` stops pending work and retains geometry. `undo` issues one native
   undo only for a single closed sketch-edit transaction and compares model
   checkpoints. It rejects changed checkpoints and groups containing manual
   edits. For “undo the agent's edit but retain my manual edit,” resume/finish
   the manual request, then start a **new** agent request with a fresh checkpoint.
7. **Acceptance coverage:** unit tests cover state transitions, deduplication,
   stale selections, handoff, exact constraint readback, guarded undo and driver
   sharing. A real local Chromium fixture checks target rendering, editing an
   input and immutable images. These do not establish live Onshape correctness.

## Client recipe

Call `onshape_workflow(command="begin", request_id="unique-stable-id", goal=..., steps=...)`.
Each step is `{ "tool": "sketch.start", "args": {"plane": "Top"}, "space": "px" }`.
Use the same request ID only when retrying the same initial request.
Call `next` once; show the returned image; repeat only when the user wants to proceed.
Supported workflow commands: begin, next, pause, resume, revise, handoff, cancel,
undo, status, restore. Completion means the supplied steps executed, not that
all dimensions have been independently verified.

After drawing a rough rectangle, call `onshape_frame`, then select an edge using
that frame's ID. Show the marker and ask the user to confirm it. Queue the edit
with `revise` (not `resume`, which expires handles):

```json
{
  "command": "revise",
  "steps": [{
    "tool": "selection.edit",
    "args": {
      "handle": "HANDLE_FROM_SELECTION",
      "operation": "add_dimension",
      "confirmed": true,
      "value_mm": 35,
      "label_x": 300,
      "label_y": 180
    },
    "space": "px"
  }]
}
```

The label coordinates above are illustrative: select real coordinates from the
current image. To change an existing dimension use `operation="dimension"` on
its label. To move a point use `operation="move", x, y` (destination pixels).
For a relationship use `operation="constraint", constraint_type, handles` where
`handles` contains other fresh targets. Each edit consumes the selections.

## Reusable client prompt

```text
Use the shared Onshape interactive workflow, not FeatureScript or the M4 API tool.
Start one request with a stable ID. Execute one step, show its inline image, and
let me steer. Draw rough geometry first. Highlight a target and ask me to confirm
it before editing. Re-observe and reselect after every resize or zoom; never reuse
old pixel locations. Keep applied and verified separate. After committing, inspect
entity/constraint IDs and read back requested dimensions. If an action fails, inspect
partial state rather than recreate the sketch. Pause for my manual edits and resume
from the actual drawing. Never undo across my manual changes.
```

## Live acceptance still required

On a disposable document: draw a rectangle, dimension each edge separately, add
and position a circle, edit a dimension label, drag a spline control point, test
conflicting constraints, hand off a manual change, start a fresh agent edit, and
undo it while retaining the manual change. Repeat after zooming and on different
planes. The existing selector bindings, native undo grouping and persisted feature
response need this live validation. There is no automatic CAD entity tracker yet:
ambiguous or moved targets require a fresh visual selection. Exact screenshot
freshness checks are conservative and may pause on cosmetic UI changes.
