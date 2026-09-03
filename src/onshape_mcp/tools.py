"""The Onshape tool datasheet — the boring 80% of the work.

Each entry is one *semantic* op the agent can perform. The actual low-level
clicks live in driver.py. This file is the vocabulary the LLM uses.

Status legend:
  planned  - not yet wired up
  stub     - registered but raises NotImplementedError
  working  - tested manually
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    name: str
    purpose: str
    requires: list[str] = field(default_factory=list)  # preconditions
    produces: list[str] = field(default_factory=list)  # postconditions
    next_steps: list[str] = field(default_factory=list)  # likely follow-ups
    status: str = "planned"


# ─── sketch ────────────────────────────────────────────────────────────────
SKETCH_START = ToolSpec(
    name="sketch.start",
    purpose="Open a new sketch on a chosen plane (Top/Front/Right or a face).",
    produces=["sketch.active=true"],
    next_steps=["sketch.rectangle", "sketch.circle", "sketch.line", "sketch.spline"],
    status="planned",
)
SKETCH_RECTANGLE = ToolSpec(
    name="sketch.rectangle",
    purpose="Two-corner rectangle. Pass corner1=(x,y), corner2=(x,y) in sketch units.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "feature.extrude", "sketch.mirror"],
    status="planned",
)
SKETCH_CIRCLE = ToolSpec(
    name="sketch.circle",
    purpose="Center + radius. center=(x,y), radius=mm.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "feature.extrude"],
    status="planned",
)
SKETCH_LINE = ToolSpec(
    name="sketch.line",
    purpose="Single line segment from p1 to p2.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.constrain"],
    status="planned",
)
SKETCH_SPLINE = ToolSpec(
    name="sketch.spline",
    purpose="Open spline through control points [(x,y), ...].",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.constrain"],
    status="planned",
)
SKETCH_DIMENSION = ToolSpec(
    name="sketch.dimension",
    purpose="Drive a linear / radial / angular dimension to a numeric value.",
    requires=["sketch.active=true"],
    next_steps=["sketch.constrain", "feature.extrude"],
    status="planned",
)
SKETCH_CONSTRAIN = ToolSpec(
    name="sketch.constrain",
    purpose="Add a geometric constraint (coincident / horizontal / vertical / equal / tangent / etc.).",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="planned",
)
SKETCH_MIRROR = ToolSpec(
    name="sketch.mirror",
    purpose="Mirror entities in the active sketch across a line.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit", "feature.extrude"],
    status="planned",
)
SKETCH_EXIT = ToolSpec(
    name="sketch.exit",
    purpose="Close the active sketch and return to part studio.",
    requires=["sketch.active=true"],
    produces=["sketch.active=false"],
    next_steps=["feature.extrude", "feature.revolve", "feature.fillet", "feature.chamfer"],
    status="planned",
)

# ─── features ───────────────────────────────────────────────────────────────
FEATURE_EXTRUDE = ToolSpec(
    name="feature.extrude",
    purpose="Extrude the active sketch region by depth, optionally with draft/taper.",
    requires=["sketch.active=false", "sketch.closed=true"],
    next_steps=["feature.fillet", "feature.chamfer", "feature.shell", "feature.pattern"],
    status="planned",
)
FEATURE_REVOLVE = ToolSpec(
    name="feature.revolve",
    purpose="Revolve a sketch region around an axis by an angle.",
    requires=["sketch.active=false", "sketch.closed=true"],
    next_steps=["feature.fillet", "feature.chamfer"],
    status="planned",
)
FEATURE_FILLET = ToolSpec(
    name="feature.fillet",
    purpose="Round selected edges with a constant or variable radius.",
    next_steps=["feature.chamfer", "feature.shell", "feature.pattern"],
    status="planned",
)
FEATURE_CHAMFER = ToolSpec(
    name="feature.chamfer",
    purpose="Bevel selected edges, distance or distance+angle.",
    next_steps=["feature.fillet", "feature.shell", "feature.pattern"],
    status="planned",
)
FEATURE_SHELL = ToolSpec(
    name="feature.shell",
    purpose="Hollow a body, removing selected faces, with a wall thickness.",
    next_steps=["feature.fillet", "feature.pattern"],
    status="planned",
)
FEATURE_PATTERN = ToolSpec(
    name="feature.pattern",
    purpose="Linear or circular pattern of features / faces / bodies.",
    next_steps=["feature.mirror_body", "assembly.mate"],
    status="planned",
)
FEATURE_MIRROR_BODY = ToolSpec(
    name="feature.mirror_body",
    purpose="Mirror bodies across a plane in the part studio.",
    next_steps=["feature.pattern", "assembly.mate"],
    status="planned",
)

# ─── selection / view ──────────────────────────────────────────────────────
SELECT_FACE = ToolSpec(
    name="select.face",
    purpose="Click a face in the viewport. Pass face_id (or rely on vision pick).",
    next_steps=["sketch.start", "feature.extrude", "feature.fillet"],
    status="planned",
)
SELECT_EDGE = ToolSpec(
    name="select.edge",
    purpose="Click an edge in the viewport.",
    next_steps=["feature.fillet", "feature.chamfer"],
    status="planned",
)
SELECT_BODY = ToolSpec(
    name="select.body",
    purpose="Click a body in the viewport or the feature tree.",
    next_steps=["assembly.mate", "feature.mirror_body"],
    status="planned",
)
VIEW_FIT = ToolSpec(
    name="view.fit",
    purpose="Reframe the camera to fit all visible bodies.",
    next_steps=["select.face", "sketch.start"],
    status="planned",
)
VIEW_ROTATE = ToolSpec(
    name="view.rotate",
    purpose="Orbit the camera by (dx, dy) drag.",
    next_steps=["view.fit", "select.face"],
    status="planned",
)

# ─── assembly ──────────────────────────────────────────────────────────────
ASSEMBLY_MATE = ToolSpec(
    name="assembly.mate",
    purpose="Create a mate between two faces / edges / vertices.",
    next_steps=["assembly.mate", "assembly.pattern"],
    status="planned",
)
ASSEMBLY_PATTERN = ToolSpec(
    name="assembly.pattern",
    purpose="Pattern instances in an assembly.",
    status="planned",
)

# ─── document / meta ───────────────────────────────────────────────────────
DOC_OPEN = ToolSpec(
    name="doc.open",
    purpose="Navigate to a document by URL or docId/elementId.",
    next_steps=["view.fit", "sketch.start"],
    status="planned",
)
DOC_SAVE = ToolSpec(
    name="doc.save",
    purpose="Force a save (Onshape auto-saves, this just makes the journal honest).",
    status="planned",
)
UNDO = ToolSpec(
    name="ui.undo",
    purpose="Send the standard Undo shortcut (Ctrl/Cmd+Z).",
    next_steps=["ui.redo", "view.fit"],
    status="planned",
)
REDO = ToolSpec(
    name="ui.redo",
    purpose="Send Redo (Ctrl/Cmd+Shift+Z).",
    next_steps=["ui.undo", "view.fit"],
    status="planned",
)


ALL_TOOLS: list[ToolSpec] = [
    SKETCH_START, SKETCH_RECTANGLE, SKETCH_CIRCLE, SKETCH_LINE, SKETCH_SPLINE,
    SKETCH_DIMENSION, SKETCH_CONSTRAIN, SKETCH_MIRROR, SKETCH_EXIT,
    FEATURE_EXTRUDE, FEATURE_REVOLVE, FEATURE_FILLET, FEATURE_CHAMFER,
    FEATURE_SHELL, FEATURE_PATTERN, FEATURE_MIRROR_BODY,
    SELECT_FACE, SELECT_EDGE, SELECT_BODY, VIEW_FIT, VIEW_ROTATE,
    ASSEMBLY_MATE, ASSEMBLY_PATTERN,
    DOC_OPEN, DOC_SAVE, UNDO, REDO,
]


def as_prompt_block() -> str:
    """Render the datasheet as a compact prompt block for the LLM."""
    lines = ["# Onshape tool vocabulary", ""]
    for t in ALL_TOOLS:
        bits = [f"**{t.name}** — {t.purpose}"]
        if t.requires:
            bits.append(f"  requires: {', '.join(t.requires)}")
        if t.produces:
            bits.append(f"  produces: {', '.join(t.produces)}")
        if t.next_steps:
            bits.append(f"  next: {', '.join(t.next_steps)}")
        bits.append(f"  status: {t.status}")
        lines.extend(bits)
    return "\n".join(lines)


def lookup(name: str) -> ToolSpec:
    for t in ALL_TOOLS:
        if t.name == name:
            return t
    raise KeyError(f"Unknown tool: {name}")
