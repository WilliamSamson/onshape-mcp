"""Onshape UI bindings. Keyboard shortcuts and toolbar button labels.

This is the bridge between the semantic tool vocabulary in tools.py and
the actual UI. Onshape changes this occasionally; when an action fails,
this is the first place to check.

Confidence flags: high (tested or well-documented), medium (plausible,
not yet verified), low (guess based on convention).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Binding:
    keys: tuple[str, ...] | None = None
    toolbar_text: str | None = None  # visible label / aria-label
    toolbar_role: str = "button"
    notes: str = ""
    confidence: str = "medium"


# ─── view / camera ────────────────────────────────────────────────────────
VIEW_FIT = Binding(keys=("f",), confidence="high", notes="Fit all; 'F' in viewport")
VIEW_TOP = Binding(keys=("7",), confidence="low")
VIEW_FRONT = Binding(keys=("1",), confidence="low")
VIEW_ISO = Binding(keys=("F2",), confidence="low")

# ─── sketching ────────────────────────────────────────────────────────────
# Onshape sketch tools: you click the tool in the left toolbar, then click
# in the viewport. There isn't a universal "start sketch" shortcut. You
# click the sketch button or a plane, then a tool.
SKETCH_START = Binding(
    toolbar_text="Sketch",
    toolbar_role="button",
    confidence="high",
    notes="Click the 'Sketch' button in the left toolbar, then click a plane or face.",
)
SKETCH_RECTANGLE = Binding(
    toolbar_text="Rectangle",
    toolbar_role="button",
    confidence="high",
    notes="After entering a sketch, click the rectangle tool, then click 2 corners.",
)
SKETCH_CIRCLE = Binding(toolbar_text="Circle", toolbar_role="button", confidence="high")
SKETCH_LINE = Binding(toolbar_text="Line", toolbar_role="button", confidence="high")
SKETCH_SPLINE = Binding(toolbar_text="Spline", toolbar_role="button", confidence="medium")
SKETCH_DIMENSION = Binding(keys=("d",), confidence="medium", notes="In a sketch only.")
SKETCH_MIRROR = Binding(toolbar_text="Mirror", toolbar_role="button", confidence="medium")
SKETCH_EXIT = Binding(
    keys=("Escape",),
    confidence="high",
    notes="Press Esc to exit the current sketch tool. May need 2 presses if a subtool is active.",
)

# ─── features ─────────────────────────────────────────────────────────────
FEATURE_EXTRUDE = Binding(
    keys=("e",),
    toolbar_text="Extrude",
    toolbar_role="button",
    confidence="high",
    notes="With a closed sketch region selected, press E or click Extrude.",
)
FEATURE_REVOLVE = Binding(
    keys=("r",),
    toolbar_text="Revolve",
    toolbar_role="button",
    confidence="medium",
)
FEATURE_FILLET = Binding(
    keys=("f",),
    toolbar_text="Fillet",
    toolbar_role="button",
    confidence="medium",
    notes="'F' collides with view.fit when nothing is selected. Prefer toolbar click.",
)
FEATURE_CHAMFER = Binding(toolbar_text="Chamfer", toolbar_role="button", confidence="high")
FEATURE_SHELL = Binding(toolbar_text="Shell", toolbar_role="button", confidence="high")
FEATURE_PATTERN = Binding(toolbar_text="Pattern", toolbar_role="button", confidence="medium")
FEATURE_MIRROR_BODY = Binding(toolbar_text="Mirror", toolbar_role="button", confidence="medium")

# ─── assembly / meta ──────────────────────────────────────────────────────
ASSEMBLY_MATE = Binding(toolbar_text="Mate", toolbar_role="button", confidence="high")
ASSEMBLY_PATTERN = Binding(toolbar_text="Pattern", toolbar_role="button", confidence="medium")

# ─── global ───────────────────────────────────────────────────────────────
UNDO = Binding(keys=("Control", "z"), confidence="high")
REDO = Binding(keys=("Control", "shift", "z"), confidence="high")
SAVE = Binding(keys=("Control", "s"), confidence="high", notes="Onshape auto-saves; this is a no-op but the shortcut still works.")
DESELECT = Binding(keys=("Escape",), confidence="high")
CONFIRM = Binding(keys=("Enter",), confidence="high")
DELETE = Binding(keys=("Delete",), confidence="high")


# Map datasheet tool name -> binding.
BINDINGS: dict[str, Binding] = {
    "view.fit": VIEW_FIT,
    "view.top": VIEW_TOP,
    "view.front": VIEW_FRONT,
    "view.iso": VIEW_ISO,
    "view.rotate": Binding(
        notes="Middle-mouse drag (no fixed coords). The LLM passes start/end via the call.",
        confidence="high",
    ),
    "sketch.start": SKETCH_START,
    "sketch.rectangle": SKETCH_RECTANGLE,
    "sketch.circle": SKETCH_CIRCLE,
    "sketch.line": SKETCH_LINE,
    "sketch.spline": SKETCH_SPLINE,
    "sketch.dimension": SKETCH_DIMENSION,
    "sketch.constrain": Binding(
        toolbar_text="Coincident",  # default; many sub-tools in the flyout
        toolbar_role="button",
        notes="The constraint flyout has many buttons (Coincident, Horizontal, Vertical, Equal, Tangent, …). The LLM picks a coordinate on the geometry and we'll choose the right one. May need refactor to accept constraint type as an arg.",
        confidence="medium",
    ),
    "sketch.mirror": SKETCH_MIRROR,
    "sketch.exit": SKETCH_EXIT,
    "feature.extrude": FEATURE_EXTRUDE,
    "feature.revolve": FEATURE_REVOLVE,
    "feature.fillet": FEATURE_FILLET,
    "feature.chamfer": FEATURE_CHAMFER,
    "feature.shell": FEATURE_SHELL,
    "feature.pattern": FEATURE_PATTERN,
    "feature.mirror_body": FEATURE_MIRROR_BODY,
    "assembly.mate": ASSEMBLY_MATE,
    "assembly.pattern": ASSEMBLY_PATTERN,
    # Selection is just a click. No shortcut or button. The binding is the
    # act of clicking a coordinate in the viewport; ui_actions handles it.
    "select.face": Binding(notes="Click in viewport at (x,y); ui_actions handles the click.", confidence="high"),
    "select.edge": Binding(notes="Click in viewport at (x,y).", confidence="high"),
    "select.body": Binding(notes="Click in viewport or in the feature tree.", confidence="high"),
    "ui.undo": UNDO,
    "ui.redo": REDO,
    "doc.save": SAVE,
    "ui.deselect": DESELECT,
    "ui.confirm": CONFIRM,
    "ui.delete": DELETE,
}


def get(tool_name: str) -> Binding:
    try:
        return BINDINGS[tool_name]
    except KeyError as e:
        raise KeyError(f"No UI binding for {tool_name!r} in shortcuts.py") from e
