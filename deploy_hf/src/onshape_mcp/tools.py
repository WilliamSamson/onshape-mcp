"""Onshape tool datasheet. One entry per semantic op the agent can call.
The actual clicks live in ui_actions.py / driver.py. This file is the
vocabulary the LLM sees via the `tool_datasheet` MCP tool.

Status flags: planned, stub, working.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    purpose: str
    requires: list[str] = field(default_factory=list)  # preconditions
    produces: list[str] = field(default_factory=list)  # postconditions
    next_steps: list[str] = field(default_factory=list)  # likely follow-ups
    status: str = "working"


# Sketch lifecycle
SKETCH_START = ToolSpec(
    name="sketch.start",
    purpose="Open a new sketch on a chosen plane (Top/Front/Right or a face).",
    produces=["sketch.active=true"],
    next_steps=["sketch.rectangle", "sketch.circle", "sketch.line", "sketch.spline"],
    status="working",
)
SKETCH_EXIT = ToolSpec(
    name="sketch.exit",
    purpose="Close the active sketch and return to part studio.",
    requires=["sketch.active=true"],
    produces=["sketch.active=false"],
    next_steps=["feature.extrude", "feature.revolve", "feature.fillet", "feature.chamfer"],
    status="working",
)

# Sketch Primitives
SKETCH_LINE = ToolSpec(
    name="sketch.line",
    purpose="Single line segment from p1=(x1,y1) to p2=(x2,y2).",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.constrain", "sketch.exit"],
    status="working",
)
SKETCH_LINE_MIDPOINT = ToolSpec(
    name="sketch.line_midpoint",
    purpose="Line segment symmetric around a midpoint coordinate.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_RECTANGLE = ToolSpec(
    name="sketch.rectangle",
    purpose="Two-corner rectangle. Pass quadrant='1'|'2'|'3'|'4', centered=true, or corner1=(x,y), corner2=(x,y), with width/height (e.g. '10 cm' or 50).",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "feature.extrude", "sketch.exit"],
    status="working",
)
SKETCH_RECTANGLE_CENTER = ToolSpec(
    name="sketch.rectangle_center",
    purpose="Center-point rectangle defined by center=(x,y) and corner=(x,y) or width/height.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "feature.extrude", "sketch.exit"],
    status="working",
)
SKETCH_RECTANGLE_ALIGNED = ToolSpec(
    name="sketch.rectangle_aligned",
    purpose="3-point aligned rectangle defined by baseline (p1, p2) and height point p3.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_CIRCLE = ToolSpec(
    name="sketch.circle",
    purpose="Center point circle. Pass centered=true (for origin) or center=(x,y), radius=mm or radius_px.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "feature.extrude", "sketch.exit"],
    status="working",
)
SKETCH_CIRCLE_3POINT = ToolSpec(
    name="sketch.circle_3point",
    purpose="Circle passing through three points p1, p2, p3.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_ELLIPSE = ToolSpec(
    name="sketch.ellipse",
    purpose="Ellipse defined by center=(x,y), major axis point, and minor axis point.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_ARC = ToolSpec(
    name="sketch.arc",
    purpose="3-point arc from p1 to p2 passing through radius/point p3.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_ARC_TANGENT = ToolSpec(
    name="sketch.arc_tangent",
    purpose="Arc tangent to an existing line/curve starting at vertex p1 ending at p2.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_ARC_CENTER = ToolSpec(
    name="sketch.arc_center",
    purpose="Center point arc defined by center=(x,y), start angle/point p1, end angle/point p2.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_POLYGON = ToolSpec(
    name="sketch.polygon",
    purpose="Inscribed or circumscribed polygon with center=(x,y), radius=r, and sides=n (e.g. 6 for hexagon).",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "feature.extrude", "sketch.exit"],
    status="working",
)
SKETCH_SPLINE = ToolSpec(
    name="sketch.spline",
    purpose="Spline through control points [(x1,y1), (x2,y2), ...].",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_POINT = ToolSpec(
    name="sketch.point",
    purpose="Single point at (x,y).",
    requires=["sketch.active=true"],
    next_steps=["sketch.constrain", "sketch.exit"],
    status="working",
)
SKETCH_TEXT = ToolSpec(
    name="sketch.text",
    purpose="Text box defined by corner1=(x,y), corner2=(x,y), and text string.",
    requires=["sketch.active=true"],
    next_steps=["feature.extrude", "sketch.exit"],
    status="working",
)
SKETCH_USE = ToolSpec(
    name="sketch.use",
    purpose="Project 3D edge or face onto active sketch plane.",
    requires=["sketch.active=true"],
    next_steps=["sketch.offset", "sketch.trim", "sketch.exit"],
    status="working",
)

# Modifications & Operations
SKETCH_CONSTRUCTION = ToolSpec(
    name="sketch.construction",
    purpose="Toggle construction mode or convert entity at (x,y) to/from construction line ('q').",
    requires=["sketch.active=true"],
    next_steps=["sketch.line", "sketch.circle", "sketch.exit"],
    status="working",
)
SKETCH_FILLET = ToolSpec(
    name="sketch.fillet",
    purpose="Create a 2D rounded fillet at vertex (x,y) or between two curves with radius_mm.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_CHAMFER = ToolSpec(
    name="sketch.chamfer",
    purpose="Create a 2D chamfer at vertex (x,y) with distance_mm.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_TRIM = ToolSpec(
    name="sketch.trim",
    purpose="Trim a curve segment at (x,y) back to the nearest intersections ('m').",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_EXTEND = ToolSpec(
    name="sketch.extend",
    purpose="Extend an endpoint at (x,y) forward to the next curve boundary ('x').",
    requires=["sketch.active=true"],
    next_steps=["sketch.trim", "sketch.exit"],
    status="working",
)
SKETCH_SPLIT = ToolSpec(
    name="sketch.split",
    purpose="Split curve into two segments at coordinate (x,y).",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)
SKETCH_OFFSET = ToolSpec(
    name="sketch.offset",
    purpose="Offset entity at (x,y) by distance_mm to target side.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_SLOT = ToolSpec(
    name="sketch.slot",
    purpose="Create an elongated slot along a line segment with a given width/radius.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
SKETCH_MIRROR = ToolSpec(
    name="sketch.mirror",
    purpose="Mirror entities across a centerline (line_xy, entities=[(x,y), ...]).",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit", "feature.extrude"],
    status="working",
)
SKETCH_PATTERN_LINEAR = ToolSpec(
    name="sketch.pattern_linear",
    purpose="Linear pattern of entities along X and Y axes with counts and spacings.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)
SKETCH_PATTERN_CIRCULAR = ToolSpec(
    name="sketch.pattern_circular",
    purpose="Circular pattern of entities around center=(x,y) with count and angle.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)
SKETCH_TRANSFORM = ToolSpec(
    name="sketch.transform",
    purpose="Translate, scale, or rotate selected entities.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)

# Dimensions & Constraints
SKETCH_DIMENSION = ToolSpec(
    name="sketch.dimension",
    purpose="Apply a driven linear, radial, or angular dimension (entity_xy, label_xy, value).",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit", "feature.extrude"],
    status="working",
)
CONSTRAINT_COINCIDENT = ToolSpec(
    name="constraint.coincident",
    purpose="Make two points coincident, or point coincident to a curve.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_CONCENTRIC = ToolSpec(
    name="constraint.concentric",
    purpose="Make two arcs or circles share the same center point.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_PARALLEL = ToolSpec(
    name="constraint.parallel",
    purpose="Make two lines parallel ('b').",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_TANGENT = ToolSpec(
    name="constraint.tangent",
    purpose="Make an arc/circle tangent to a line or another arc ('t').",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_HORIZONTAL = ToolSpec(
    name="constraint.horizontal",
    purpose="Make a line horizontal or align two points horizontally ('h').",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_VERTICAL = ToolSpec(
    name="constraint.vertical",
    purpose="Make a line vertical or align two points vertically ('v').",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_PERPENDICULAR = ToolSpec(
    name="constraint.perpendicular",
    purpose="Make two lines perpendicular (90 degrees).",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_EQUAL = ToolSpec(
    name="constraint.equal",
    purpose="Constrain two lines to equal length, or two circles/arcs to equal radius ('e').",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_MIDPOINT = ToolSpec(
    name="constraint.midpoint",
    purpose="Constrain a point to the midpoint of a line segment.",
    requires=["sketch.active=true"],
    next_steps=["sketch.dimension", "sketch.exit"],
    status="working",
)
CONSTRAINT_NORMAL = ToolSpec(
    name="constraint.normal",
    purpose="Constrain a curve normal to a plane.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)
CONSTRAINT_PIERCE = ToolSpec(
    name="constraint.pierce",
    purpose="Constrain a point to the pierce point of an intersecting 3D curve.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)
CONSTRAINT_SYMMETRIC = ToolSpec(
    name="constraint.symmetric",
    purpose="Constrain two entities symmetrically across a centerline.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)
CONSTRAINT_FIX = ToolSpec(
    name="constraint.fix",
    purpose="Fix an entity in place preventing solver movement.",
    requires=["sketch.active=true"],
    next_steps=["sketch.exit"],
    status="working",
)

# Feature tools
FEATURE_EXTRUDE = ToolSpec(
    name="feature.extrude",
    purpose="Extrude the active sketch region by depth, optionally with draft/taper.",
    requires=["sketch.active=false"],
    next_steps=["feature.fillet", "feature.chamfer", "feature.shell", "feature.pattern"],
    status="working",
)
FEATURE_REVOLVE = ToolSpec(
    name="feature.revolve",
    purpose="Revolve a sketch region around an axis by an angle.",
    requires=["sketch.active=false"],
    next_steps=["feature.fillet", "feature.chamfer"],
    status="working",
)
FEATURE_FILLET = ToolSpec(
    name="feature.fillet",
    purpose="Round selected 3D edges with a constant radius.",
    next_steps=["feature.chamfer", "feature.shell", "feature.pattern"],
    status="working",
)
FEATURE_CHAMFER = ToolSpec(
    name="feature.chamfer",
    purpose="Bevel selected 3D edges with a distance.",
    next_steps=["feature.fillet", "feature.shell", "feature.pattern"],
    status="working",
)
FEATURE_SHELL = ToolSpec(
    name="feature.shell",
    purpose="Hollow a body, removing selected faces, with a wall thickness.",
    next_steps=["feature.fillet", "feature.pattern"],
    status="working",
)
FEATURE_PATTERN = ToolSpec(
    name="feature.pattern",
    purpose="Linear or circular pattern of features / faces / bodies.",
    next_steps=["feature.mirror_body", "assembly.mate"],
    status="working",
)
FEATURE_MIRROR_BODY = ToolSpec(
    name="feature.mirror_body",
    purpose="Mirror bodies across a plane in the part studio.",
    next_steps=["feature.pattern", "assembly.mate"],
    status="working",
)

# Selection and view
SELECT_FACE = ToolSpec(
    name="select.face",
    purpose="Click a face in the viewport at (x,y).",
    next_steps=["sketch.start", "feature.extrude", "feature.fillet"],
    status="working",
)
SELECT_EDGE = ToolSpec(
    name="select.edge",
    purpose="Click an edge in the viewport at (x,y).",
    next_steps=["feature.fillet", "feature.chamfer"],
    status="working",
)
SELECT_BODY = ToolSpec(
    name="select.body",
    purpose="Click a body in the viewport or feature tree.",
    next_steps=["feature.mirror_body"],
    status="working",
)
VIEW_FIT = ToolSpec(
    name="view.fit",
    purpose="Zoom to fit all visible geometry in viewport ('f').",
    status="working",
)
VIEW_ROTATE = ToolSpec(
    name="view.rotate",
    purpose="Right-mouse drag from start to end to orbit the camera.",
    status="working",
)
ASSEMBLY_MATE = ToolSpec(
    name="assembly.mate",
    purpose="Create a mate between two mate connectors.",
    status="planned",
)
ASSEMBLY_PATTERN = ToolSpec(
    name="assembly.pattern",
    purpose="Pattern an instance in an assembly.",
    status="planned",
)
DOC_OPEN = ToolSpec(
    name="doc.open",
    purpose="Navigate to an Onshape document by URL.",
    status="working",
)
DOC_SAVE = ToolSpec(
    name="doc.save",
    purpose="No-op; Onshape auto-saves continuously.",
    status="working",
)
UNDO = ToolSpec(
    name="ui.undo",
    purpose="Send the standard Undo shortcut (Ctrl/Cmd+Z).",
    next_steps=["ui.redo", "view.fit"],
    status="working",
)
REDO = ToolSpec(
    name="ui.redo",
    purpose="Send Redo (Ctrl/Cmd+Shift+Z).",
    next_steps=["ui.undo", "view.fit"],
    status="working",
)

ALL_TOOLS: list[ToolSpec] = [
    # Lifecycle
    SKETCH_START,
    SKETCH_EXIT,
    # Primitives
    SKETCH_LINE,
    SKETCH_LINE_MIDPOINT,
    SKETCH_RECTANGLE,
    SKETCH_RECTANGLE_CENTER,
    SKETCH_RECTANGLE_ALIGNED,
    SKETCH_CIRCLE,
    SKETCH_CIRCLE_3POINT,
    SKETCH_ELLIPSE,
    SKETCH_ARC,
    SKETCH_ARC_TANGENT,
    SKETCH_ARC_CENTER,
    SKETCH_POLYGON,
    SKETCH_SPLINE,
    SKETCH_POINT,
    SKETCH_TEXT,
    SKETCH_USE,
    # Operations
    SKETCH_CONSTRUCTION,
    SKETCH_FILLET,
    SKETCH_CHAMFER,
    SKETCH_TRIM,
    SKETCH_EXTEND,
    SKETCH_SPLIT,
    SKETCH_OFFSET,
    SKETCH_SLOT,
    SKETCH_MIRROR,
    SKETCH_PATTERN_LINEAR,
    SKETCH_PATTERN_CIRCULAR,
    SKETCH_TRANSFORM,
    # Dimensions & Constraints
    SKETCH_DIMENSION,
    CONSTRAINT_COINCIDENT,
    CONSTRAINT_CONCENTRIC,
    CONSTRAINT_PARALLEL,
    CONSTRAINT_TANGENT,
    CONSTRAINT_HORIZONTAL,
    CONSTRAINT_VERTICAL,
    CONSTRAINT_PERPENDICULAR,
    CONSTRAINT_EQUAL,
    CONSTRAINT_MIDPOINT,
    CONSTRAINT_NORMAL,
    CONSTRAINT_PIERCE,
    CONSTRAINT_SYMMETRIC,
    CONSTRAINT_FIX,
    # Features
    FEATURE_EXTRUDE,
    FEATURE_REVOLVE,
    FEATURE_FILLET,
    FEATURE_CHAMFER,
    FEATURE_SHELL,
    FEATURE_PATTERN,
    FEATURE_MIRROR_BODY,
    SELECT_FACE,
    SELECT_EDGE,
    SELECT_BODY,
    VIEW_FIT,
    VIEW_ROTATE,
    ASSEMBLY_MATE,
    ASSEMBLY_PATTERN,
    DOC_OPEN,
    DOC_SAVE,
    UNDO,
    REDO,
]


def as_prompt_block() -> str:
    """Render the datasheet as a compact prompt block for the LLM."""
    lines = ["# Onshape tool vocabulary", ""]
    for t in ALL_TOOLS:
        bits = [f"**{t.name}** {t.purpose}"]
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
