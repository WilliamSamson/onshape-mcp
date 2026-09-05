"""Onshape UI bindings. Keyboard shortcuts and toolbar button labels.

This is the bridge between the semantic tool vocabulary in tools.py and
the actual UI. Onshape changes this occasionally; when an action fails,
this is the first place to check.

Confidence flags: high (tested or well-documented), medium (plausible,
not yet verified), low (guess based on convention).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Binding:
    keys: tuple[str, ...] | None = None
    toolbar_text: str | None = None  # visible label / aria-label
    toolbar_role: str = "button"
    notes: str = ""
    confidence: str = "medium"


# View and camera
VIEW_FIT = Binding(keys=("f",), confidence="high", notes="Fit all; 'F' in viewport")
VIEW_TOP = Binding(keys=("7",), confidence="low")
VIEW_FRONT = Binding(keys=("1",), confidence="low")
VIEW_ISO = Binding(keys=("Shift", "7"), confidence="high", notes="Isometric view: Shift+7")

# Sketch start and exit
SKETCH_START = Binding(
    toolbar_text="Sketch",
    toolbar_role="button",
    confidence="high",
    notes="Click the 'Sketch' button in the left toolbar, then click a plane or face.",
)
SKETCH_EXIT = Binding(
    keys=("Escape",),
    confidence="high",
    notes="Press Esc to exit the current sketch tool.",
)

# Sketch Primitives
SKETCH_LINE = Binding(
    keys=("l",),
    toolbar_text="Line",
    toolbar_role="button",
    confidence="high",
    notes="Line tool shortcut 'l'. Click start, click end.",
)
SKETCH_LINE_MIDPOINT = Binding(
    toolbar_text="Midpoint line",
    toolbar_role="button",
    confidence="medium",
    notes="Line anchored at midpoint.",
)
SKETCH_RECTANGLE = Binding(
    keys=("g",),
    toolbar_text="Rectangle",
    toolbar_role="button",
    confidence="high",
    notes="Corner rectangle shortcut 'g'.",
)
SKETCH_RECTANGLE_CENTER = Binding(
    keys=("r",),
    toolbar_text="Center point rectangle",
    toolbar_role="button",
    confidence="high",
    notes="Center point rectangle shortcut 'r'.",
)
SKETCH_RECTANGLE_ALIGNED = Binding(
    toolbar_text="Aligned rectangle",
    toolbar_role="button",
    confidence="medium",
    notes="3-point aligned rectangle.",
)
SKETCH_CIRCLE = Binding(
    keys=("c",),
    toolbar_text="Circle",
    toolbar_role="button",
    confidence="high",
    notes="Center point circle shortcut 'c'.",
)
SKETCH_CIRCLE_3POINT = Binding(
    toolbar_text="3 point circle",
    toolbar_role="button",
    confidence="medium",
    notes="Circle defined by 3 perimeter points.",
)
SKETCH_ELLIPSE = Binding(
    toolbar_text="Ellipse",
    toolbar_role="button",
    confidence="medium",
    notes="Center point and major/minor axes.",
)
SKETCH_ARC = Binding(
    keys=("a",),
    toolbar_text="Arc",
    toolbar_role="button",
    confidence="high",
    notes="3-point arc shortcut 'a'. Click start, click end, click radius point.",
)
SKETCH_ARC_3POINT = SKETCH_ARC
SKETCH_ARC_TANGENT = Binding(
    toolbar_text="Tangent arc",
    toolbar_role="button",
    confidence="medium",
    notes="Arc tangent to an existing line or curve.",
)
SKETCH_ARC_CENTER = Binding(
    toolbar_text="Center point arc",
    toolbar_role="button",
    confidence="medium",
    notes="Center point, start angle, end angle.",
)
SKETCH_ARC_ELLIPTICAL = Binding(
    toolbar_text="Elliptical arc",
    toolbar_role="button",
    confidence="medium",
)
SKETCH_CONIC = Binding(
    toolbar_text="Conic",
    toolbar_role="button",
    confidence="medium",
)
SKETCH_POLYGON = Binding(
    toolbar_text="Inscribed polygon",
    toolbar_role="button",
    confidence="high",
    notes="Inscribed polygon. Click center, click radius, type side count.",
)
SKETCH_POLYGON_INSCRIBED = SKETCH_POLYGON
SKETCH_POLYGON_CIRCUMSCRIBED = Binding(
    toolbar_text="Circumscribed polygon",
    toolbar_role="button",
    confidence="medium",
)
SKETCH_SPLINE = Binding(
    toolbar_text="Spline",
    toolbar_role="button",
    confidence="medium",
    notes="Spline through control points.",
)
SKETCH_BEZIER = Binding(
    toolbar_text="Bezier",
    toolbar_role="button",
    confidence="medium",
)
SKETCH_POINT = Binding(
    toolbar_text="Point",
    toolbar_role="button",
    confidence="high",
    notes="Single sketch point.",
)
SKETCH_TEXT = Binding(
    toolbar_text="Text",
    toolbar_role="button",
    confidence="high",
    notes="Text in sketch. Drag bounding box, enter string.",
)
SKETCH_USE = Binding(
    keys=("u",),
    toolbar_text="Use",
    toolbar_role="button",
    confidence="high",
    notes="Project existing geometry onto sketch plane ('u').",
)
SKETCH_INTERSECTION = Binding(
    toolbar_text="Intersection",
    toolbar_role="button",
    confidence="medium",
)

# Modifications & Operations
SKETCH_CONSTRUCTION = Binding(
    keys=("q",),
    toolbar_text="Construction",
    toolbar_role="button",
    confidence="high",
    notes="Toggle construction geometry on/off ('q').",
)
SKETCH_FILLET = Binding(
    keys=("Shift", "f"),
    toolbar_text="Fillet",
    toolbar_role="button",
    confidence="high",
    notes="Sketch fillet between two lines or at a vertex ('Shift+f').",
)
SKETCH_CHAMFER = Binding(
    toolbar_text="Chamfer",
    toolbar_role="button",
    confidence="medium",
    notes="Sketch chamfer at corner.",
)
SKETCH_TRIM = Binding(
    keys=("m",),
    toolbar_text="Trim",
    toolbar_role="button",
    confidence="high",
    notes="Trim curve to nearest intersection ('m').",
)
SKETCH_EXTEND = Binding(
    keys=("x",),
    toolbar_text="Extend",
    toolbar_role="button",
    confidence="high",
    notes="Extend curve to boundary ('x').",
)
SKETCH_SPLIT = Binding(
    toolbar_text="Split",
    toolbar_role="button",
    confidence="medium",
    notes="Split curve at point.",
)
SKETCH_OFFSET = Binding(
    keys=("o",),
    toolbar_text="Offset",
    toolbar_role="button",
    confidence="high",
    notes="Offset selected sketch curve ('o').",
)
SKETCH_SLOT = Binding(
    toolbar_text="Slot",
    toolbar_role="button",
    confidence="medium",
)
SKETCH_MIRROR = Binding(
    toolbar_text="Mirror",
    toolbar_role="button",
    confidence="high",
    notes="Mirror entities across a centerline.",
)
SKETCH_PATTERN_LINEAR = Binding(
    toolbar_text="Linear pattern",
    toolbar_role="button",
    confidence="medium",
)
SKETCH_PATTERN_CIRCULAR = Binding(
    toolbar_text="Circular pattern",
    toolbar_role="button",
    confidence="medium",
)
SKETCH_TRANSFORM = Binding(
    toolbar_text="Transform",
    toolbar_role="button",
    confidence="medium",
)

# Dimension & Constraints
SKETCH_DIMENSION = Binding(
    keys=("d",),
    toolbar_text="Dimension",
    toolbar_role="button",
    confidence="high",
    notes="Drive linear/angular/radial dimension ('d').",
)
CONSTRAINT_COINCIDENT = Binding(
    keys=("i",),
    toolbar_text="Coincident",
    toolbar_role="button",
    confidence="high",
    notes="Coincident constraint ('i').",
)
CONSTRAINT_CONCENTRIC = Binding(
    toolbar_text="Concentric",
    toolbar_role="button",
    confidence="high",
    notes="Concentric constraint between two circles/arcs.",
)
CONSTRAINT_PARALLEL = Binding(
    keys=("b",),
    toolbar_text="Parallel",
    toolbar_role="button",
    confidence="high",
    notes="Parallel constraint between two lines ('b').",
)
CONSTRAINT_TANGENT = Binding(
    keys=("t",),
    toolbar_text="Tangent",
    toolbar_role="button",
    confidence="high",
    notes="Tangent constraint ('t').",
)
CONSTRAINT_HORIZONTAL = Binding(
    keys=("h",),
    toolbar_text="Horizontal",
    toolbar_role="button",
    confidence="high",
    notes="Horizontal constraint ('h').",
)
CONSTRAINT_VERTICAL = Binding(
    keys=("v",),
    toolbar_text="Vertical",
    toolbar_role="button",
    confidence="high",
    notes="Vertical constraint ('v').",
)
CONSTRAINT_PERPENDICULAR = Binding(
    toolbar_text="Perpendicular",
    toolbar_role="button",
    confidence="high",
    notes="Perpendicular constraint between two lines.",
)
CONSTRAINT_EQUAL = Binding(
    keys=("e",),
    toolbar_text="Equal",
    toolbar_role="button",
    confidence="high",
    notes="Equal length/radius constraint ('e').",
)
CONSTRAINT_MIDPOINT = Binding(
    toolbar_text="Midpoint",
    toolbar_role="button",
    confidence="high",
    notes="Midpoint constraint between point and line.",
)
CONSTRAINT_NORMAL = Binding(
    toolbar_text="Normal",
    toolbar_role="button",
    confidence="medium",
    notes="Normal constraint to plane or surface.",
)
CONSTRAINT_PIERCE = Binding(
    toolbar_text="Pierce",
    toolbar_role="button",
    confidence="medium",
    notes="Pierce constraint between point and curve intersecting plane.",
)
CONSTRAINT_SYMMETRIC = Binding(
    toolbar_text="Symmetric",
    toolbar_role="button",
    confidence="medium",
    notes="Symmetric constraint across a centerline.",
)
CONSTRAINT_FIX = Binding(
    toolbar_text="Fix",
    toolbar_role="button",
    confidence="high",
    notes="Fix entity in place.",
)
CONSTRAINT_CURVATURE = Binding(
    toolbar_text="Curvature",
    toolbar_role="button",
    confidence="medium",
    notes="Curvature continuous constraint.",
)

# Feature tools
FEATURE_EXTRUDE = Binding(
    keys=("Shift", "e"),
    toolbar_text="Extrude",
    toolbar_role="button",
    confidence="high",
    notes="With a closed sketch region selected, press Shift+E or click Extrude.",
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

# Assembly and meta
ASSEMBLY_MATE = Binding(toolbar_text="Mate", toolbar_role="button", confidence="high")
ASSEMBLY_PATTERN = Binding(toolbar_text="Pattern", toolbar_role="button", confidence="medium")

# Global bindings
UNDO = Binding(keys=("Control", "z"), confidence="high")
REDO = Binding(keys=("Control", "shift", "z"), confidence="high")
SAVE = Binding(
    keys=("Control", "s"),
    confidence="high",
    notes="Onshape auto-saves; this is a no-op but the shortcut still works.",
)
DESELECT = Binding(keys=("Escape",), confidence="high")
CONFIRM = Binding(keys=("Enter",), confidence="high")
DELETE = Binding(keys=("Delete",), confidence="high")

# Map datasheet tool name -> binding.
BINDINGS: dict[str, Binding] = {
    "view.fit": VIEW_FIT,
    "view.top": VIEW_TOP,
    "view.front": VIEW_FRONT,
    "view.iso": VIEW_ISO,
    "view.isometric": VIEW_ISO,
    "view.rotate": Binding(
        notes="Middle-mouse drag (no fixed coords). The LLM passes start/end via the call.",
        confidence="high",
    ),
    # Sketch lifecycle
    "sketch.start": SKETCH_START,
    "sketch.exit": SKETCH_EXIT,
    "sketch.m4_profile": Binding(
        confidence="high",
        notes="Exact geometry is created with the authenticated Onshape Feature API.",
    ),
    # Sketch Primitives
    "sketch.line": SKETCH_LINE,
    "sketch.line_midpoint": SKETCH_LINE_MIDPOINT,
    "sketch.rectangle": SKETCH_RECTANGLE,
    "sketch.rectangle_center": SKETCH_RECTANGLE_CENTER,
    "sketch.rectangle_aligned": SKETCH_RECTANGLE_ALIGNED,
    "sketch.circle": SKETCH_CIRCLE,
    "sketch.circle_3point": SKETCH_CIRCLE_3POINT,
    "sketch.ellipse": SKETCH_ELLIPSE,
    "sketch.arc": SKETCH_ARC,
    "sketch.arc_3point": SKETCH_ARC_3POINT,
    "sketch.arc_tangent": SKETCH_ARC_TANGENT,
    "sketch.arc_center": SKETCH_ARC_CENTER,
    "sketch.arc_elliptical": SKETCH_ARC_ELLIPTICAL,
    "sketch.conic": SKETCH_CONIC,
    "sketch.polygon": SKETCH_POLYGON,
    "sketch.polygon_inscribed": SKETCH_POLYGON_INSCRIBED,
    "sketch.polygon_circumscribed": SKETCH_POLYGON_CIRCUMSCRIBED,
    "sketch.spline": SKETCH_SPLINE,
    "sketch.bezier": SKETCH_BEZIER,
    "sketch.point": SKETCH_POINT,
    "sketch.text": SKETCH_TEXT,
    "sketch.use": SKETCH_USE,
    "sketch.intersection": SKETCH_INTERSECTION,
    # Operations
    "sketch.construction": SKETCH_CONSTRUCTION,
    "sketch.fillet": SKETCH_FILLET,
    "sketch.chamfer": SKETCH_CHAMFER,
    "sketch.trim": SKETCH_TRIM,
    "sketch.extend": SKETCH_EXTEND,
    "sketch.split": SKETCH_SPLIT,
    "sketch.offset": SKETCH_OFFSET,
    "sketch.slot": SKETCH_SLOT,
    "sketch.mirror": SKETCH_MIRROR,
    "sketch.pattern_linear": SKETCH_PATTERN_LINEAR,
    "sketch.pattern_circular": SKETCH_PATTERN_CIRCULAR,
    "sketch.transform": SKETCH_TRANSFORM,
    # Dimensions & Constraints
    "sketch.dimension": SKETCH_DIMENSION,
    "sketch.equal": CONSTRAINT_EQUAL,
    "sketch.constrain": CONSTRAINT_COINCIDENT,
    "constraint.coincident": CONSTRAINT_COINCIDENT,
    "constraint.concentric": CONSTRAINT_CONCENTRIC,
    "constraint.parallel": CONSTRAINT_PARALLEL,
    "constraint.tangent": CONSTRAINT_TANGENT,
    "constraint.horizontal": CONSTRAINT_HORIZONTAL,
    "constraint.vertical": CONSTRAINT_VERTICAL,
    "constraint.perpendicular": CONSTRAINT_PERPENDICULAR,
    "constraint.equal": CONSTRAINT_EQUAL,
    "constraint.midpoint": CONSTRAINT_MIDPOINT,
    "constraint.normal": CONSTRAINT_NORMAL,
    "constraint.pierce": CONSTRAINT_PIERCE,
    "constraint.symmetric": CONSTRAINT_SYMMETRIC,
    "constraint.fix": CONSTRAINT_FIX,
    "constraint.curvature": CONSTRAINT_CURVATURE,
    # Features
    "feature.extrude": FEATURE_EXTRUDE,
    "feature.revolve": FEATURE_REVOLVE,
    "feature.fillet": FEATURE_FILLET,
    "feature.chamfer": FEATURE_CHAMFER,
    "feature.shell": FEATURE_SHELL,
    "feature.pattern": FEATURE_PATTERN,
    "feature.mirror_body": FEATURE_MIRROR_BODY,
    "assembly.mate": ASSEMBLY_MATE,
    "assembly.pattern": ASSEMBLY_PATTERN,
    "select.face": Binding(
        notes="Click in viewport at (x,y); ui_actions handles the click.", confidence="high"
    ),
    "select.edge": Binding(notes="Click in viewport at (x,y).", confidence="high"),
    "select.body": Binding(notes="Click in viewport or in the feature tree.", confidence="high"),
    "ui.undo": UNDO,
    "ui.redo": REDO,
    "ui.wait": Binding(
        notes="No-op. Pauses for N seconds and screenshots. Use when the LLM wants to re-observe the viewport.",
        confidence="high",
    ),
    "doc.save": SAVE,
    "doc.new": Binding(
        toolbar_text="Create",
        toolbar_role="button",
        notes="Create a new document. Or just navigate to /documents/new.",
        confidence="medium",
    ),
    "ui.deselect": DESELECT,
    "ui.confirm": CONFIRM,
    "ui.delete": DELETE,
}


def get(tool_name: str) -> Binding:
    try:
        return BINDINGS[tool_name]
    except KeyError as e:
        raise KeyError(f"No UI binding for {tool_name!r} in shortcuts.py") from e
