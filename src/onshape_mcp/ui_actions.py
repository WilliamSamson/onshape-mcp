"""High-level Onshape operations. Each public function corresponds to a
datasheet tool. Uses driver.py primitives + shortcuts.py bindings, journals
to journal.py. Raises before touching the UI if a precondition isn't met.

Conventions: every function takes the driver explicitly (no globals), returns
a `Result` dict, and uses viewport pixel coords. Call `driver.viewport_box()`
to get bounds.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import settings
from .driver import OnshapeDriver
from .journal import JournalEntry, journal
from .onshape_api import create_m4_profile
from .shortcuts import get as binding_for


@dataclass
class Result:
    ok: bool
    note: str = ""
    screenshot: Path | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok, "note": self.note}
        if self.screenshot is not None:
            d["screenshot"] = str(self.screenshot)
        d.update(self.meta)
        return d


def _record(tool: str, args: dict[str, Any], result: Result) -> None:
    e = JournalEntry.new(tool, args)
    e.result = "ok" if result.ok else "fail"
    e.note = result.note
    if result.screenshot is not None:
        try:
            e.screenshot = str(result.screenshot.relative_to(result.screenshot.parent.parent))
        except Exception:
            e.screenshot = str(result.screenshot)
    journal.append(e)


# View and camera


async def view_fit(d: OnshapeDriver) -> Result:
    b = binding_for("view.fit")
    if b.keys:
        await d.press_chord(*b.keys)
    elif b.toolbar_text:
        ok = await d.click_text(b.toolbar_text)
        if not ok:
            return Result(False, f"view.fit: toolbar button {b.toolbar_text!r} not found")
    shot = await d.screenshot("view_fit.png")
    r = Result(True, "fit to view", shot)
    _record("view.fit", {}, r)
    return r


async def view_top(d: OnshapeDriver) -> Result:
    b = binding_for("view.top")
    if b.keys:
        await d.press_chord(*b.keys)
    shot = await d.screenshot("view_top.png")
    r = Result(True, "top view", shot)
    _record("view.top", {}, r)
    return r


async def view_front(d: OnshapeDriver) -> Result:
    b = binding_for("view.front")
    if b.keys:
        await d.press_chord(*b.keys)
    shot = await d.screenshot("view_front.png")
    r = Result(True, "front view", shot)
    _record("view.front", {}, r)
    return r


async def view_iso(d: OnshapeDriver) -> Result:
    b = binding_for("view.iso")
    if b.keys:
        await d.press_chord(*b.keys)
    shot = await d.screenshot("view_isometric.png")
    r = Result(True, "isometric view", shot)
    _record("view.iso", {}, r)
    return r


view_isometric = view_iso


async def m4_profile_exact(d: OnshapeDriver, length_mm: float = 20.0) -> Result:
    """Create and API-verify an exact M4 socket-head revolve half-profile."""
    verification = await create_m4_profile(
        d,
        length_mm=float(length_mm),
        name=f"M4x{float(length_mm):g} Exact Profile",
    )
    shot = await d.screenshot("m4_profile_exact.png")
    r = Result(
        bool(verification["ok"]),
        "created and verified exact M4 revolve profile"
        if verification["ok"]
        else f"M4 profile verification failed: {verification['errors']}",
        shot,
        verification,
    )
    _record("sketch.m4_profile", {"length_mm": length_mm}, r)
    return r

# Sketching


async def sketch_start(
    d: OnshapeDriver,
    plane_xy: tuple[float, float] | None = None,
    plane_name: str | None = None,
    plane: str | None = None,
) -> Result:
    """Click the Sketch button, then click a plane (or pass a coordinate/name).

    If `plane_xy` is None, we select the desired plane in the feature tree
    using DOM locator (default: Top plane) and press 'n' to orient normal to the sketch plane.
    """
    target_plane = plane or plane_name or "Top"
    sketch_btn = d.page.locator("[command-id='newSketch']")
    if await sketch_btn.count() > 0:
        await sketch_btn.first.click()
    else:
        b = binding_for("sketch.start")
        clicked = False
        if b.toolbar_text:
            clicked = await d.click_text(b.toolbar_text, timeout_ms=500)
        if not clicked and b.keys:
            await d.press_chord(*b.keys)
            clicked = True
        if not clicked:
            # Previously fell through to a hardcoded click at (155, 58),
            # which silently hits whatever is at that pixel in a layout
            # we don't recognise. Failing is the honest outcome.
            return Result(False, "sketch.start: no Sketch button, toolbar text, or key binding found")
    # small settle delay for the UI to switch into plane-pick mode
    await asyncio.sleep(0.3)

    target_name = target_plane.capitalize()
    if plane_xy is not None:
        await d.click(*plane_xy)
        await asyncio.sleep(0.4)
        try:
            await d.page.locator("canvas").first.hover()
        except Exception:
            pass
        await d.press_key("n")
    else:
        # Use exact DOM locator for feature tree plane
        loc = d.page.locator("span.os-list-item-name", has_text=target_name)
        if await loc.count() > 0:
            await loc.first.click()
            await asyncio.sleep(0.3)
            # Once a plane is selected Onshape enters sketch mode.  Right-clicking
            # the plane at this point reselects the tree and can cancel/derail the
            # new sketch. Focus the canvas and use Onshape's documented normal-view
            # shortcut instead.
            try:
                await d.page.locator("canvas").first.hover()
            except Exception:
                pass
            await d.press_key("n")
        else:
            return Result(
                False,
                f"sketch.start: plane {target_name!r} not found in the feature tree",
            )
    active_dialog = d.page.locator(".feature-dialog:not(.ns-dialog-default-hidden)")
    try:
        await active_dialog.first.wait_for(state="visible", timeout=5000)
    except Exception:
        pass
    if await active_dialog.count() == 0:
        shot = await d.screenshot("sketch_start_failed.png")
        r = Result(False, f"Onshape did not enter sketch mode on {target_name}", shot)
        _record("sketch.start", {"plane": target_name}, r)
        return r
    shot = await d.screenshot("sketch_start.png")
    r = Result(True, f"sketch started on {target_name}", shot, {"plane": target_name})
    _record("sketch.start", {"plane": target_name}, r)
    return r


SKETCH_COMMAND_IDS: dict[str, str] = {
    "sketch.start": "newSketch",
    "sketch.line": "LINESEGMENT",
    "sketch.line_midpoint": "LINESEGMENT_MIDPOINT",
    "sketch.rectangle": "RECTANGLE_TWO_CORNERS",
    "sketch.rectangle_center": "RECTANGLE_CENTER_CORNER",
    "sketch.rectangle_aligned": "ALIGNED_RECTANGLE",
    "sketch.circle": "CIRCLE_CENTER_RADIUS",
    "sketch.circle_3point": "CIRCLE_THREE_POINTS",
    "sketch.ellipse": "ELLIPSE",
    "sketch.arc": "ARC_START_END_RADIUS",
    "sketch.arc_3point": "ARC_START_END_RADIUS",
    "sketch.arc_tangent": "ARC_TANGENT",
    "sketch.arc_center": "ARC_CENTER_START_END",
    "sketch.polygon": "INSCRIBED_POLYGON",
    "sketch.polygon_inscribed": "INSCRIBED_POLYGON",
    "sketch.polygon_circumscribed": "CIRCUMSCRIBED_POLYGON",
    "sketch.spline": "SPLINE",
    "sketch.bezier": "BEZIER",
    "sketch.point": "POINT",
    "sketch.text": "TEXT_RECTANGLE_TWO_CORNERS",
    "sketch.use": "USE",
    "sketch.intersection": "INTERSECTION",
    "sketch.construction": "TOGGLE_CONSTRUCTION",
    "sketch.fillet": "FILLET",
    "sketch.chamfer": "SKETCH_CHAMFER",
    "sketch.trim": "TRIM",
    "sketch.extend": "EXTEND",
    "sketch.split": "SPLIT",
    "sketch.offset": "OFFSET",
    "sketch.slot": "SLOT",
    "sketch.mirror": "SKETCHMIRROR",
    "sketch.pattern_linear": "SKETCHLPATTERN",
    "sketch.pattern_circular": "SKETCHCPATTERN",
    "sketch.transform": "SKETCH_TRANSFORM",
    "sketch.dimension": "DIMENSION",
    # Constraints
    "sketch.equal": "EQUAL",
    "constraint.coincident": "COINCIDENT",
    "constraint.concentric": "CONCENTRIC",
    "constraint.parallel": "PARALLEL",
    "constraint.tangent": "TANGENT",
    "constraint.horizontal": "HORIZONTAL",
    "constraint.vertical": "VERTICAL",
    "constraint.perpendicular": "PERPENDICULAR",
    "constraint.equal": "EQUAL",
    "constraint.midpoint": "MIDPOINT",
    "constraint.normal": "NORMAL",
    "constraint.pierce": "PIERCE",
    "constraint.symmetric": "MIRROR",
    "constraint.fix": "FIX",
    "constraint.curvature": "CURVATURE",
    # 3D Features
    "feature.extrude": "extrude",
    "feature.revolve": "revolve",
}


def _as_mm_str(val: float | str) -> str:
    return f"{val:g} mm" if isinstance(val, (int, float)) else str(val)


async def _enter_value(d: OnshapeDriver, val: float | str) -> str:
    """Type a dimension into whatever Onshape input is live, then commit.

    Onshape sometimes renders an `input.os-canvas-text-edit` and sometimes
    takes raw keystrokes; this was copy-pasted in five places.
    """
    text = _as_mm_str(val)
    dim_input = d.page.locator("input.os-canvas-text-edit")
    if await dim_input.count() > 0:
        await dim_input.first.fill(text)
    else:
        await d.type_text(text)
    await asyncio.sleep(0.1)
    await d.press_key("Enter")
    await asyncio.sleep(0.3)
    return text


async def _commit_dialog(d: OnshapeDriver) -> bool:
    """Click the green checkmark that commits a feature dialog."""
    ok = d.page.locator(
        ".ns-dialog-button-ok, .button-ok, button[aria-label*='check' i], button[title*='check' i]"
    ).first
    try:
        if await ok.count() > 0 and await ok.is_visible():
            await ok.click()
            await asyncio.sleep(0.3)
            return True
    except Exception:
        pass
    return False


async def _activate_sketch_tool(d: OnshapeDriver, name: str) -> Result:
    """Activate a sketch tool via DOM command-id, keyboard shortcut, or text locator."""
    # 1. Try keyboard shortcut first if available (fastest, most reliable)
    b = binding_for(name)
    if b.keys:
        await d.press_chord(*b.keys)
        await asyncio.sleep(0.2)
        return Result(True, f"{name} tool active (keys: {b.keys})")

    # 2. Try direct DOM command-id locator
    cmd_id = SKETCH_COMMAND_IDS.get(name)
    if cmd_id:
        loc = d.page.locator(f"[command-id='{cmd_id}']")
        if await loc.count() > 0 and await loc.first.is_visible():
            classes = await loc.first.get_attribute("class") or ""
            if "is-active" in classes:
                return Result(True, f"{name} already active")
            await loc.first.click()
            await asyncio.sleep(0.25)
            return Result(True, f"{name} tool active (command-id: {cmd_id})")

    # 3. Fall back to visible toolbar text
    if b.toolbar_text:
        clicked = await d.click_text(b.toolbar_text, timeout_ms=1000)
        if clicked:
            await asyncio.sleep(0.2)
            return Result(True, f"{name} tool active (text: {b.toolbar_text})")

    return Result(False, f"{name}: no binding or visible tool button available")


def parse_mm(val: float | str | None, default_mm: float | None = None) -> float | None:
    """Parse a dimension to millimetres. Bare numbers are millimetres —
    the unit every tool signature and docstring in this package documents.

    There is deliberately no magnitude-based unit guessing here: guessing
    made a 10 that meant 10mm silently become 100mm.
    """
    if val is None:
        return default_mm
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().lower()
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return default_mm
    num = float(m.group(0))
    if "cm" in s:
        return num * 10.0
    if "in" in s:  # covers "in" and "inch"
        return num * 25.4
    if "m" in s and "mm" not in s:  # bare metres
        return num * 1000.0
    return num


async def get_canvas_origin(d: OnshapeDriver) -> tuple[float, float]:
    """Calculate the exact center point (origin) of the WebGL canvas."""
    try:
        box = await d.page.evaluate("""() => {
            const c = document.querySelector('canvas.os-main-canvas') || document.querySelector('canvas');
            if (!c) return null;
            const r = c.getBoundingClientRect();
            return {cx: r.x + r.width / 2.0, cy: r.y + r.height / 2.0, h: r.height, w: r.width};
        }""")
        if box:
            return (float(box["cx"]), float(box["cy"]))
    except Exception:
        pass
    return (843.0, 473.0)


# Onshape's default fit for a fresh sketch shows roughly this much of the
# model plane across the canvas height. Used only to pick pixels that land
# somewhere sane on screen — never as a measurement. True sizes come from
# sketch_dimension driving Onshape's solver.
#
# ponytail: assumes the default zoom. If the user has zoomed, drawn shapes
# come out the wrong on-screen size (the driven dimension still corrects
# them). Set ONSHAPE_PX_PER_MM to pin it, or upgrade to measuring a drawn
# entity of known mm length and solving for the ratio.
DEFAULT_VIEW_SPAN_MM: float = 276.0


async def px_per_mm(d: OnshapeDriver) -> float:
    """Pixels per millimetre for *drawing*, derived from the live canvas
    height so it tracks the viewport instead of assuming 1440x900.
    """
    override = settings.px_per_mm_override.strip()
    if override:
        try:
            return float(override)
        except ValueError:
            pass
    try:
        h = await d.page.evaluate("""() => {
            const c = document.querySelector('canvas.os-main-canvas') || document.querySelector('canvas');
            return c ? c.getBoundingClientRect().height : null;
        }""")
        if h:
            return float(h) / DEFAULT_VIEW_SPAN_MM
    except Exception:
        pass
    return 900.0 / DEFAULT_VIEW_SPAN_MM


# Which space incoming coordinates are in. The vision loop reasons over
# screenshots and can only speak viewport pixels; every other caller
# (intent parser, sketch_create, the MCP tool signatures) speaks CAD mm.
# Tagging it explicitly replaced a magnitude heuristic that silently read
# a 300mm coordinate as pixels.
COORD_SPACE: ContextVar[str] = ContextVar("coord_space", default="mm")


@contextmanager
def _px_space():
    """Pass already-resolved viewport pixels into a nested ui_action
    without it converting them a second time.
    """
    token = COORD_SPACE.set("px")
    try:
        yield
    finally:
        COORD_SPACE.reset(token)


async def _ensure_viewport_coords(d: OnshapeDriver, pt: tuple[float, float]) -> tuple[float, float]:
    x, y = float(pt[0]), float(pt[1])
    if COORD_SPACE.get() == "px":
        return (x, y)
    cx, cy = await get_canvas_origin(d)
    if x == 0 and y == 0:
        return (cx, cy)
    scale = await px_per_mm(d)
    # CAD Cartesian coordinates in mm: +X is right, +Y is up (screen Y is down)
    return (cx + x * scale, cy - y * scale)


async def _span_px(d: OnshapeDriver, mm: float | None, default_mm: float) -> tuple[float, bool]:
    """Convert a mm span to a drawable pixel span. Returns (px, clamped).

    Clamping keeps the click on the canvas for very large or very small
    parts; the caller reports it rather than silently resizing the part.
    """
    scale = await px_per_mm(d)
    raw = (default_mm if mm is None else mm) * scale
    px = max(40.0, min(550.0, abs(raw)))
    return px, px != abs(raw)


async def sketch_rectangle(
    d: OnshapeDriver,
    corner1: tuple[float, float] | None = None,
    corner2: tuple[float, float] | None = None,
    width: float | str | None = None,
    height: float | str | None = None,
    quadrant: str | int | None = None,
    centered: bool | None = None,
) -> Result:
    if await d.page.locator(".feature-dialog:not(.ns-dialog-default-hidden)").count() == 0:
        return Result(False, "sketch.rectangle requires an active sketch")

    cx, cy = await get_canvas_origin(d)
    w_mm = parse_mm(width)
    h_mm = parse_mm(height)
    span_x, clamp_x = await _span_px(d, w_mm, default_mm=36.0)
    span_y, clamp_y = await _span_px(d, h_mm, default_mm=36.0)

    # Quadrant / centered anchor the rectangle relative to the on-screen
    # origin, so those branches produce viewport pixels directly. Only
    # caller-supplied corners go through the space conversion.
    q = str(quadrant).upper().strip() if quadrant is not None else None
    quad_signs = {
        "1": (1, -1), "I": (1, -1), "TOP-RIGHT": (1, -1), "NE": (1, -1),
        "2": (-1, -1), "II": (-1, -1), "TOP-LEFT": (-1, -1), "NW": (-1, -1),
        "3": (-1, 1), "III": (-1, 1), "BOTTOM-LEFT": (-1, 1), "SW": (-1, 1),
        "4": (1, 1), "IV": (1, 1), "BOTTOM-RIGHT": (1, 1), "SE": (1, 1),
    }
    if q in quad_signs:
        sx, sy = quad_signs[q]
        c1, c2 = (cx, cy), (cx + sx * span_x, cy + sy * span_y)
    elif centered or (corner1 is None and corner2 is None):
        c1 = (cx - span_x / 2.0, cy - span_y / 2.0)
        c2 = (cx + span_x / 2.0, cy + span_y / 2.0)
    else:
        c1 = await _ensure_viewport_coords(
            d, corner1 if corner1 is not None else (cx - span_x / 2.0, cy - span_y / 2.0)
        )
        c2 = await _ensure_viewport_coords(
            d, corner2 if corner2 is not None else (cx + span_x / 2.0, cy + span_y / 2.0)
        )

    t = await _activate_sketch_tool(d, "sketch.rectangle")
    if not t.ok:
        _record("sketch.rectangle", {"corner1": list(c1), "corner2": list(c2)}, t)
        return t
    await d.click(*c1)
    await asyncio.sleep(0.3)
    await d.click(*c2)
    await asyncio.sleep(0.3)
    await d.press_key("Escape")
    await asyncio.sleep(0.3)

    min_x, max_x = min(c1[0], c2[0]), max(c1[0], c2[0])
    min_y, max_y = min(c1[1], c2[1]), max(c1[1], c2[1])
    # Pick points at 30% along edges to safely avoid datum axis lines and origin glyphs
    dx = max_x - min_x
    dy = max_y - min_y
    top_pick = (min_x + dx * 0.3, min_y)
    left_pick = (min_x, min_y + dy * 0.3)
    top_label = (top_pick[0], top_pick[1] - 45.0)
    left_label = (left_pick[0] - 55.0, left_pick[1])

    # Drive the solver with the true mm values. The pixels above only had
    # to land a rough rectangle on screen; these dimensions are what makes
    # it the requested size.
    async def _dimension_edge(along: str, value: float) -> bool:
        """Dimension one edge, retrying at a few points along it.

        Picking an edge is flaky — whichever attempt runs first tends to
        miss, so a single fixed point silently left one side undriven.
        Walking the edge costs one extra click on the rare retry.
        """
        for frac in (0.3, 0.55, 0.75):
            if along == "top":
                pick = (min_x + dx * frac, min_y)
                label = (pick[0], pick[1] - 45.0)
            else:
                pick = (min_x, min_y + dy * frac)
                label = (pick[0] - 55.0, pick[1])
            if (await sketch_dimension(d, pick, label, value)).ok:
                return True
            await asyncio.sleep(0.4)
        return False

    driven: dict[str, bool] = {}
    with _px_space():
        if w_mm is not None and h_mm is not None and w_mm == h_mm:
            # Square: Equal constraint first so it stays strictly equilateral
            await sketch_equal(d, top_pick, left_pick)
            await asyncio.sleep(0.5)
            driven["width"] = await _dimension_edge("top", w_mm)
            driven["height"] = driven["width"]  # Equal constraint carries it
        else:
            if w_mm is not None:
                driven["width"] = await _dimension_edge("top", w_mm)
                await asyncio.sleep(0.6)
            if h_mm is not None:
                driven["height"] = await _dimension_edge("left", h_mm)

    shot = await d.screenshot("sketch_rectangle.png")
    meta: dict[str, Any] = {
        "corner1": list(c1),
        "corner2": list(c2),
        "last_vertex": list(c2),
        "width_mm": w_mm,
        "height_mm": h_mm,
        "quadrant": quadrant,
        "centered": centered,
    }
    if clamp_x or clamp_y:
        meta["draw_scale_clamped"] = True
    meta["dimensions_driven"] = driven
    # A dimension that did not land means the side is only as accurate as
    # the pixels it was drawn at. Say so instead of claiming success.
    undriven = [k for k, v in driven.items() if not v]
    ok = not undriven
    note = f"rectangle {w_mm}x{h_mm} mm"
    if undriven:
        note += f" — WARNING: {', '.join(undriven)} not dimensioned, that side is approximate"
    elif clamp_x or clamp_y:
        note += " (drawn at clamped on-screen size; driven dimensions are exact)"
    r = Result(ok, note, shot, meta)
    _record("sketch.rectangle", meta, r)
    return r


async def sketch_circle(
    d: OnshapeDriver,
    center: tuple[float, float] | None = None,
    radius_mm: float | str | None = None,
    centered: bool | None = None,
) -> Result:
    t = await _activate_sketch_tool(d, "sketch.circle")
    if not t.ok:
        _record("sketch.circle", {"radius_mm": radius_mm}, t)
        return t
    cx, cy = await get_canvas_origin(d)
    if centered or center is None or tuple(center) == (0, 0):
        c = (cx, cy)
    else:
        c = await _ensure_viewport_coords(d, center)
    r_mm = parse_mm(radius_mm, default_mm=20.0)
    r_px, clamped = await _span_px(d, r_mm, default_mm=20.0)
    await d.click(*c)
    await asyncio.sleep(0.1)
    edge = (c[0] + r_px, c[1])
    await d.click(*edge)
    await asyncio.sleep(0.1)
    await d.press_key("Escape")
    # The two clicks above only place a rough circle. Drive the real
    # radius through the solver so the part is the requested size
    # regardless of zoom.
    with _px_space():
        await sketch_dimension(d, edge, (edge[0] + 50.0, edge[1] - 50.0), f"{r_mm * 2:g} mm")
    shot = await d.screenshot("sketch_circle.png")
    meta: dict[str, Any] = {"center": list(c), "radius_mm": r_mm}
    if clamped:
        meta["draw_scale_clamped"] = True
    r = Result(True, f"circle r={r_mm}mm at {c}", shot, meta)
    _record("sketch.circle", meta, r)
    return r


async def sketch_line(
    d: OnshapeDriver,
    p1: tuple[float, float],
    p2: tuple[float, float],
) -> Result:
    t = await _activate_sketch_tool(d, "sketch.line")
    if not t.ok:
        _record("sketch.line", {"p1": list(p1), "p2": list(p2)}, t)
        return t
    pt1 = await _ensure_viewport_coords(d, p1)
    pt2 = await _ensure_viewport_coords(d, p2)
    await d.click(*pt1)
    await asyncio.sleep(0.05)
    await d.click(*pt2)
    await asyncio.sleep(0.05)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_line.png")
    r = Result(True, f"line {pt1} -> {pt2}", shot)
    _record("sketch.line", {"p1": list(pt1), "p2": list(pt2)}, r)
    return r


async def sketch_dimension(
    d: OnshapeDriver,
    entity_xy: tuple[float, float],
    label_xy: tuple[float, float],
    value_mm: float | str,
) -> Result:
    """Add or set a dimension. Click the entity at `entity_xy`, place the
    dimension label at `label_xy`, then type the new value + Enter.

    This is the workhorse of the "make it 5x5" workflow. Draw any
    rectangle, then call this twice (once for each side) with the
    target mm value. The LLM doesn't need to know the px-to-mm ratio
    because Onshape's solver does the conversion.
    """
    t = await _activate_sketch_tool(d, "sketch.dimension")
    if not t.ok:
        return t
    await asyncio.sleep(0.4)
    e_xy = await _ensure_viewport_coords(d, entity_xy)
    l_xy = await _ensure_viewport_coords(d, label_xy)
    # Click the entity (line/edge/circle) to dimension
    await d.page.mouse.move(*e_xy)
    await asyncio.sleep(0.15)
    await d.page.mouse.click(*e_xy)
    await asyncio.sleep(0.4)
    # Click where to place the dimension label
    await d.page.mouse.move(*l_xy)
    await asyncio.sleep(0.15)
    await d.page.mouse.click(*l_xy)
    await asyncio.sleep(0.4)

    # Onshape opens its value editor once the dimension is actually
    # attached to an entity. If it never appears the entity click missed,
    # and typing would go nowhere — this used to return ok=True anyway,
    # so a rectangle could come back claiming both sides were driven when
    # only one was.
    editor = d.page.locator("input.os-canvas-text-edit")
    try:
        await editor.first.wait_for(state="visible", timeout=3000)
    except Exception:
        await d.press_key("Escape")
        shot = await d.screenshot("sketch_dimension_missed.png")
        r = Result(False, f"sketch.dimension: nothing selectable at {e_xy}", shot)
        _record("sketch.dimension", {"entity_xy": list(e_xy)}, r)
        return r

    val_str = await _enter_value(d, value_mm)
    # Esc to drop the dimension tool, stay in sketch
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_dimension.png")
    r = Result(
        True,
        f"dimensioned {val_str} at {e_xy}",
        shot,
        {"value": val_str},
    )
    _record(
        "sketch.dimension",
        {"entity_xy": list(e_xy), "label_xy": list(l_xy), "value": val_str},
        r,
    )
    return r


async def sketch_equal(d: OnshapeDriver, *entity_xys: tuple[float, float]) -> Result:
    """Apply the Equal constraint to make two or more entities the same size.

    Workflow: activate Equal tool, click each entity in turn, press Esc.
    The LLM passes N coordinates (each on an entity to be made equal).
    """
    if len(entity_xys) < 2:
        return Result(False, "sketch.equal needs at least 2 entities")
    t = await _activate_sketch_tool(d, "sketch.equal")
    if not t.ok:
        return t
    await asyncio.sleep(0.4)
    for xy in entity_xys:
        pt = await _ensure_viewport_coords(d, xy)
        await d.page.mouse.move(*pt)
        await asyncio.sleep(0.15)
        await d.page.mouse.click(*pt)
        await asyncio.sleep(0.3)
    await d.press_key("Escape")
    await asyncio.sleep(0.4)
    shot = await d.screenshot("sketch_equal.png")
    r = Result(True, f"equal across {len(entity_xys)} entities", shot)
    _record("sketch.equal", {"entities": [list(xy) for xy in entity_xys]}, r)
    return r


async def sketch_arc(
    d: OnshapeDriver,
    p1: tuple[float, float],
    p2: tuple[float, float],
    radius_pt: tuple[float, float] | None = None,
) -> Result:
    """Create a 3-point arc from p1 to p2 passing through radius_pt."""
    t = await _activate_sketch_tool(d, "sketch.arc")
    if not t.ok:
        return t
    pt1 = await _ensure_viewport_coords(d, p1)
    pt2 = await _ensure_viewport_coords(d, p2)
    if radius_pt is not None:
        pt3 = await _ensure_viewport_coords(d, radius_pt)
    else:
        # Default arc bulge perpendicular to chord
        mx, my = (pt1[0] + pt2[0]) / 2.0, (pt1[1] + pt2[1]) / 2.0
        pt3 = (mx, my - 30.0)
    await d.click(*pt1)
    await asyncio.sleep(0.1)
    await d.click(*pt2)
    await asyncio.sleep(0.1)
    await d.click(*pt3)
    await asyncio.sleep(0.1)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_arc.png")
    r = Result(True, f"arc {pt1} -> {pt2} through {pt3}", shot)
    _record("sketch.arc", {"p1": list(pt1), "p2": list(pt2), "radius_pt": list(pt3)}, r)
    return r


async def sketch_polygon(
    d: OnshapeDriver,
    center: tuple[float, float] | None = None,
    radius_mm: float | str | None = None,
    sides: int = 6,
    circumscribed: bool = False,
) -> Result:
    """Draw an inscribed or circumscribed polygon.

    ponytail: the radius is drawn at scale but not dimension-driven —
    Onshape dimensions a polygon through its construction circle, which
    needs a second pick. Add that when polygon sizing has to be exact.
    """
    tool_name = "sketch.polygon_circumscribed" if circumscribed else "sketch.polygon_inscribed"
    t = await _activate_sketch_tool(d, tool_name)
    if not t.ok:
        t = await _activate_sketch_tool(d, "sketch.polygon")
    if not t.ok:
        return t
    cx, cy = await get_canvas_origin(d)
    c = await _ensure_viewport_coords(d, center) if center is not None else (cx, cy)
    r_mm = parse_mm(radius_mm, default_mm=25.0)
    r_px, clamped = await _span_px(d, r_mm, default_mm=25.0)
    await d.click(*c)
    await asyncio.sleep(0.15)
    await d.click(c[0] + r_px, c[1])
    await asyncio.sleep(0.2)
    await d.type_text(str(int(sides)))
    await asyncio.sleep(0.1)
    await d.press_key("Enter")
    await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_polygon.png")
    meta: dict[str, Any] = {"center": list(c), "radius_mm": r_mm, "sides": sides}
    if clamped:
        meta["draw_scale_clamped"] = True
    r = Result(True, f"{sides}-sided polygon r={r_mm}mm at {c}", shot, meta)
    _record("sketch.polygon", meta, r)
    return r


async def sketch_spline(d: OnshapeDriver, points: list[tuple[float, float]]) -> Result:
    """Draw a spline passing through a sequence of points."""
    if len(points) < 2:
        return Result(False, "sketch.spline requires at least 2 points")
    t = await _activate_sketch_tool(d, "sketch.spline")
    if not t.ok:
        return t
    pts = [await _ensure_viewport_coords(d, p) for p in points]
    for pt in pts:
        await d.click(*pt)
        await asyncio.sleep(0.15)
    await d.double_click(*pts[-1])
    await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_spline.png")
    r = Result(True, f"spline through {len(pts)} points", shot)
    _record("sketch.spline", {"points": [list(p) for p in pts]}, r)
    return r


async def sketch_point(d: OnshapeDriver, pt: tuple[float, float]) -> Result:
    """Place a single sketch point at coordinate pt."""
    t = await _activate_sketch_tool(d, "sketch.point")
    if not t.ok:
        return t
    p = await _ensure_viewport_coords(d, pt)
    await d.click(*p)
    await asyncio.sleep(0.1)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_point.png")
    r = Result(True, f"point at {p}", shot)
    _record("sketch.point", {"pt": list(p)}, r)
    return r


async def sketch_text(
    d: OnshapeDriver,
    corner1: tuple[float, float],
    corner2: tuple[float, float],
    text: str,
) -> Result:
    """Draw a text box from corner1 to corner2 and enter text."""
    t = await _activate_sketch_tool(d, "sketch.text")
    if not t.ok:
        return t
    c1 = await _ensure_viewport_coords(d, corner1)
    c2 = await _ensure_viewport_coords(d, corner2)
    await d.click(*c1)
    await asyncio.sleep(0.1)
    await d.click(*c2)
    await asyncio.sleep(0.3)
    # Fill in the text in the dialog
    textarea = d.page.locator("textarea.os-text-editor-input, textarea")
    if await textarea.count() > 0:
        await textarea.first.fill(text)
        await asyncio.sleep(0.1)
        ok_btn = d.page.locator(".ns-dialog-button-ok, .button-ok").first
        if await ok_btn.count() > 0:
            await ok_btn.click()
        else:
            await d.press_key("Enter")
    else:
        await d.type_text(text)
        await d.press_key("Enter")
    await asyncio.sleep(0.3)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_text.png")
    r = Result(True, f"text '{text}' at {c1}->{c2}", shot)
    _record("sketch.text", {"corner1": list(c1), "corner2": list(c2), "text": text}, r)
    return r


async def sketch_use(d: OnshapeDriver, pt: tuple[float, float]) -> Result:
    """Project existing 3D model geometry or sketch curve at pt onto sketch plane."""
    t = await _activate_sketch_tool(d, "sketch.use")
    if not t.ok:
        return t
    p = await _ensure_viewport_coords(d, pt)
    await d.click(*p)
    await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_use.png")
    r = Result(True, f"projected geometry at {p}", shot)
    _record("sketch.use", {"pt": list(p)}, r)
    return r


async def sketch_construction(d: OnshapeDriver, pt: tuple[float, float] | None = None) -> Result:
    """Toggle construction mode or convert entity at pt to construction geometry ('q')."""
    if pt is not None:
        p = await _ensure_viewport_coords(d, pt)
        await d.click(*p)
        await asyncio.sleep(0.15)
        await d.press_chord("q")
        await asyncio.sleep(0.15)
        await d.press_key("Escape")
        shot = await d.screenshot("sketch_construction.png")
        r = Result(True, f"converted entity at {p} to construction", shot)
        _record("sketch.construction", {"pt": list(p)}, r)
        return r
    await d.press_chord("q")
    await asyncio.sleep(0.15)
    shot = await d.screenshot("sketch_construction.png")
    r = Result(True, "toggled construction mode", shot)
    _record("sketch.construction", {}, r)
    return r


async def sketch_fillet(
    d: OnshapeDriver,
    vertex_xy: tuple[float, float],
    radius_mm: float | str = 5.0,
) -> Result:
    """Create a 2D sketch fillet at vertex_xy with radius_mm."""
    t = await _activate_sketch_tool(d, "sketch.fillet")
    if not t.ok:
        return t
    v = await _ensure_viewport_coords(d, vertex_xy)
    await d.click(*v)
    await asyncio.sleep(0.3)
    val_str = await _enter_value(d, radius_mm)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_fillet.png")
    r = Result(True, f"fillet {val_str} at {v}", shot)
    _record("sketch.fillet", {"vertex": list(v), "radius": val_str}, r)
    return r


async def sketch_chamfer(
    d: OnshapeDriver,
    vertex_xy: tuple[float, float],
    distance_mm: float | str = 5.0,
) -> Result:
    """Create a 2D sketch chamfer at vertex_xy with distance_mm."""
    t = await _activate_sketch_tool(d, "sketch.chamfer")
    if not t.ok:
        return t
    v = await _ensure_viewport_coords(d, vertex_xy)
    await d.click(*v)
    await asyncio.sleep(0.3)
    val_str = await _enter_value(d, distance_mm)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_chamfer.png")
    r = Result(True, f"chamfer {val_str} at {v}", shot)
    _record("sketch.chamfer", {"vertex": list(v), "distance": val_str}, r)
    return r


async def sketch_trim(d: OnshapeDriver, entity_xy: tuple[float, float]) -> Result:
    """Trim a sketch curve back to intersections by clicking it."""
    t = await _activate_sketch_tool(d, "sketch.trim")
    if not t.ok:
        return t
    p = await _ensure_viewport_coords(d, entity_xy)
    await d.click(*p)
    await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_trim.png")
    r = Result(True, f"trimmed at {p}", shot)
    _record("sketch.trim", {"entity": list(p)}, r)
    return r


async def sketch_extend(d: OnshapeDriver, endpoint_xy: tuple[float, float]) -> Result:
    """Extend a sketch curve to boundary by clicking its endpoint."""
    t = await _activate_sketch_tool(d, "sketch.extend")
    if not t.ok:
        return t
    p = await _ensure_viewport_coords(d, endpoint_xy)
    await d.click(*p)
    await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_extend.png")
    r = Result(True, f"extended at {p}", shot)
    _record("sketch.extend", {"endpoint": list(p)}, r)
    return r


async def sketch_split(d: OnshapeDriver, entity_xy: tuple[float, float]) -> Result:
    """Split a sketch curve at coordinate."""
    t = await _activate_sketch_tool(d, "sketch.split")
    if not t.ok:
        return t
    p = await _ensure_viewport_coords(d, entity_xy)
    await d.click(*p)
    await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_split.png")
    r = Result(True, f"split at {p}", shot)
    _record("sketch.split", {"entity": list(p)}, r)
    return r


async def sketch_offset(
    d: OnshapeDriver,
    entity_xy: tuple[float, float],
    distance_mm: float | str = 5.0,
    side_xy: tuple[float, float] | None = None,
) -> Result:
    """Offset selected curve by distance_mm."""
    t = await _activate_sketch_tool(d, "sketch.offset")
    if not t.ok:
        return t
    p = await _ensure_viewport_coords(d, entity_xy)
    await d.click(*p)
    await asyncio.sleep(0.2)
    if side_xy is not None:
        s = await _ensure_viewport_coords(d, side_xy)
        await d.click(*s)
    else:
        await d.click(p[0] + 20.0, p[1] + 20.0)
    await asyncio.sleep(0.2)
    val_str = await _enter_value(d, distance_mm)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_offset.png")
    r = Result(True, f"offset {val_str} at {p}", shot)
    _record("sketch.offset", {"entity": list(p), "distance": val_str}, r)
    return r


async def sketch_slot(
    d: OnshapeDriver,
    p1: tuple[float, float],
    p2: tuple[float, float],
    radius_px: float = 20.0,
) -> Result:
    """Create a sketch slot along line from p1 to p2."""
    t = await _activate_sketch_tool(d, "sketch.slot")
    if not t.ok:
        return t
    pt1 = await _ensure_viewport_coords(d, p1)
    pt2 = await _ensure_viewport_coords(d, p2)
    await d.click(*pt1)
    await asyncio.sleep(0.1)
    await d.click(*pt2)
    await asyncio.sleep(0.1)
    await d.click(pt2[0] + radius_px, pt2[1])
    await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_slot.png")
    r = Result(True, f"slot {pt1} -> {pt2}", shot)
    _record("sketch.slot", {"p1": list(pt1), "p2": list(pt2)}, r)
    return r


async def sketch_mirror(
    d: OnshapeDriver,
    centerline_xy: tuple[float, float],
    *entity_xys: tuple[float, float],
) -> Result:
    """Mirror entities across a centerline."""
    if not entity_xys:
        return Result(False, "sketch.mirror requires at least 1 entity to mirror")
    t = await _activate_sketch_tool(d, "sketch.mirror")
    if not t.ok:
        return t
    cl = await _ensure_viewport_coords(d, centerline_xy)
    await d.click(*cl)
    await asyncio.sleep(0.3)
    for xy in entity_xys:
        e = await _ensure_viewport_coords(d, xy)
        await d.click(*e)
        await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_mirror.png")
    r = Result(True, f"mirrored {len(entity_xys)} entities across {cl}", shot)
    _record("sketch.mirror", {"centerline": list(cl), "entities": [list(e) for e in entity_xys]}, r)
    return r


async def sketch_constrain(
    d: OnshapeDriver,
    constraint_type: str,
    *entity_xys: tuple[float, float],
) -> Result:
    """Apply any geometric constraint across selected entities."""
    c_type = constraint_type.lower().replace("constraint.", "").strip()
    tool_key = f"constraint.{c_type}"
    t = await _activate_sketch_tool(d, tool_key)
    if not t.ok:
        return t
    await asyncio.sleep(0.2)
    for xy in entity_xys:
        pt = await _ensure_viewport_coords(d, xy)
        await d.page.mouse.move(*pt)
        await asyncio.sleep(0.1)
        await d.page.mouse.click(*pt)
        await asyncio.sleep(0.2)
    await d.press_key("Escape")
    shot = await d.screenshot(f"constraint_{c_type}.png")
    r = Result(True, f"constraint {c_type} on {len(entity_xys)} entities", shot)
    _record(tool_key, {"entities": [list(e) for e in entity_xys]}, r)
    return r


async def sketch_exit(d: OnshapeDriver, commit: bool = True, **_kw) -> Result:
    """Exit and accept (or cancel) the active sketch."""
    before = await d.screenshot("sketch_exit_before.png")
    if commit:
        # Green checkmark on the sketch dialog. No hardcoded-pixel
        # fallback: clicking a guessed coordinate to "commit" can just as
        # easily discard the sketch.
        ok_btn = d.page.locator(".ns-dialog-button-ok, .button-ok").first
        if await ok_btn.count() == 0:
            return Result(False, "sketch.exit: commit button not found on the sketch dialog", before)
        await ok_btn.click()
        await asyncio.sleep(0.8)
    else:
        cancel_btn = d.page.locator(".ns-dialog-button-cancel, .button-cancel").first
        if await cancel_btn.count() > 0:
            await cancel_btn.click()
        else:
            await d.press_key("Escape")
    await asyncio.sleep(0.5)
    await d.press_key("Escape")
    await asyncio.sleep(0.5)
    after = await d.screenshot("sketch_exit_after.png")
    if commit and await d.page.locator(
        ".feature-dialog:not(.ns-dialog-default-hidden)"
    ).count() > 0:
        r = Result(False, "Sketch commit did not close the feature dialog", after)
        _record("sketch.exit", {"commit": commit}, r)
        return r
    r = Result(
        True, "exit sketch", after, {"before": str(before), "after": str(after), "commit": commit}
    )
    _record("sketch.exit", {"commit": commit}, r)
    return r


async def sketch_create(
    d: OnshapeDriver,
    plane: str = "Top",
    name: str | None = None,
    shapes: list[dict[str, Any]] | None = None,
) -> Result:
    """Create a complete 2D sketch with one or more shapes on the requested plane.

    Supported shapes in `shapes`:
      - {"type": "rectangle", "width_mm": 50, "height_mm": 30, "center_x": 0, "center_y": 0, "centered": true}
      - {"type": "circle", "diameter_mm": 20, "center_x": 0, "center_y": 0} (or "radius_mm")
      - {"type": "line", "p1": [0, 0], "p2": [50, 0]}
      - {"type": "lines", "points": [[0, 0], [40, 0], [40, 10], [10, 10], [10, 50], [0, 50]], "closed": true}
      - {"type": "polygon", "sides": 6, "radius_mm": 25, "center_x": 0, "center_y": 0}
      - {"type": "arc", "p1": [0, 0], "p2": [20, 20], "radius_mm": 15}
      - {"type": "point", "x": 0, "y": 0}
    """
    start_res = await sketch_start(d, plane=plane)
    if not start_res.ok:
        return start_res

    created_shapes: list[dict[str, Any]] = []
    shapes = shapes or []
    for s in shapes:
        stype = str(s.get("type", "")).lower().strip()
        if stype in ("rectangle", "box", "square"):
            w = s.get("width_mm") or s.get("width") or 50.0
            h = s.get("height_mm") or s.get("height") or w
            cx_val = float(s.get("center_x", 0.0))
            cy_val = float(s.get("center_y", 0.0))
            w_mm = parse_mm(w, default_mm=50.0)
            h_mm = parse_mm(h, default_mm=w_mm)
            if s.get("centered", True):
                c1 = (cx_val - w_mm / 2.0, cy_val - h_mm / 2.0)
                c2 = (cx_val + w_mm / 2.0, cy_val + h_mm / 2.0)
            else:
                c1 = (cx_val, cy_val)
                c2 = (cx_val + w_mm, cy_val + h_mm)
            res = await sketch_rectangle(d, corner1=c1, corner2=c2, width=w_mm, height=h_mm)
            created_shapes.append({"type": "rectangle", "ok": res.ok, "width_mm": w_mm, "height_mm": h_mm})

        elif stype in ("circle", "hole"):
            dia = s.get("diameter_mm") or s.get("diameter")
            rad = s.get("radius_mm") or s.get("radius")
            if dia is not None:
                rad_mm = parse_mm(dia, default_mm=40.0) / 2.0
            else:
                rad_mm = parse_mm(rad, default_mm=20.0)
            cx_val = float(s.get("center_x", 0.0))
            cy_val = float(s.get("center_y", 0.0))
            res = await sketch_circle(d, center=(cx_val, cy_val), radius_mm=rad_mm)
            created_shapes.append({"type": "circle", "ok": res.ok, "radius_mm": rad_mm, "center": [cx_val, cy_val]})

        elif stype in ("line", "segment"):
            p1 = s.get("p1") or s.get("start") or (0.0, 0.0)
            p2 = s.get("p2") or s.get("end") or (10.0, 0.0)
            res = await sketch_line(d, (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1])))
            created_shapes.append({"type": "line", "ok": res.ok, "p1": list(p1), "p2": list(p2)})

        elif stype in ("lines", "polyline", "path", "profile"):
            pts = s.get("points") or []
            closed = s.get("closed", False)
            line_results = []
            for j in range(len(pts) - 1):
                res = await sketch_line(d, (float(pts[j][0]), float(pts[j][1])), (float(pts[j+1][0]), float(pts[j+1][1])))
                line_results.append(res.ok)
            if closed and len(pts) > 2:
                res = await sketch_line(d, (float(pts[-1][0]), float(pts[-1][1])), (float(pts[0][0]), float(pts[0][1])))
                line_results.append(res.ok)
            created_shapes.append({"type": "polyline", "ok": all(line_results), "segments": len(line_results)})

        elif stype in ("polygon", "hex", "hexagon", "triangle"):
            sides = int(s.get("sides", 6))
            rad_mm = parse_mm(s.get("radius_mm") or s.get("radius"), default_mm=25.0)
            cx_val = float(s.get("center_x", 0.0))
            cy_val = float(s.get("center_y", 0.0))
            res = await sketch_polygon(d, center=(cx_val, cy_val), radius_mm=rad_mm, sides=sides)
            created_shapes.append({"type": "polygon", "ok": res.ok, "sides": sides, "radius_mm": rad_mm})

        elif stype in ("arc",):
            p1 = s.get("p1", (0.0, 0.0))
            p2 = s.get("p2", (20.0, 20.0))
            rad_pt = s.get("radius_pt") or ((float(p1[0]) + float(p2[0])) / 2.0, (float(p1[1]) + float(p2[1])) / 2.0 + 10.0)
            res = await sketch_arc(d, (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1])), (float(rad_pt[0]), float(rad_pt[1])))
            created_shapes.append({"type": "arc", "ok": res.ok})

        elif stype in ("point",):
            x = float(s.get("x", 0.0))
            y = float(s.get("y", 0.0))
            res = await sketch_point(d, (x, y))
            created_shapes.append({"type": "point", "ok": res.ok})

    exit_res = await sketch_exit(d, commit=True)
    shot = await d.screenshot("sketch_create.png")

    listing = await features_list(d)
    all_features = listing.meta.get("features", [])

    # The commit result was previously discarded, so a sketch that failed
    # to commit still reported ok=True with the dialog left open.
    ok = exit_res.ok and all(s.get("ok", False) for s in created_shapes)
    note = (
        f"Created sketch on {plane} with {len(created_shapes)} shape(s)"
        if ok
        else f"Sketch on {plane} incomplete: {exit_res.note}"
    )
    r = Result(
        ok,
        note,
        shot,
        {"shapes": created_shapes, "features": all_features, "plane": plane, "name": name},
    )
    _record("sketch.create", {"plane": plane, "shapes_count": len(created_shapes)}, r)
    return r


# Feature tools


async def _select_latest_sketch(d: OnshapeDriver) -> bool:
    """Click the most recent sketch in Onshape's feature tree so the
    extrude tool knows what region to use. Returns True if a sketch was
    selected, False otherwise.

    When the doc has multiple sketches, pressing E with nothing selected
    picks nothing and Onshape shows "Select face or sketch region to
    extrude". Clicking the latest sketch in the tree pre-selects it.
    """
    try:
        clicked = await d.page.evaluate(
            """() => {
                // Feature tree rows. Onshape uses a few different class
                // names across versions; grab anything that looks like
                // a tree node containing a Sketch label.
                const candidates = document.querySelectorAll(
                    '[class*="feature-tree"] [class*="item"], ' +
                    '[class*="FeatureTree"] [class*="item"], ' +
                    '[data-test*="feature-tree"] [class*="row"]'
                );
                let best = null;
                let bestNum = -1;
                for (const el of candidates) {
                    const t = (el.textContent || '').trim();
                    const m = t.match(/^Sketch\\s*(\\d+)/i);
                    if (m) {
                        const n = parseInt(m[1], 10);
                        if (n > bestNum) { bestNum = n; best = el; }
                    }
                }
                if (best) { best.click(); return true; }
                return false;
            }"""
        )
        if clicked:
            await asyncio.sleep(0.4)
        return bool(clicked)
    except Exception:
        return False


async def feature_extrude(d: OnshapeDriver, depth_mm: float | None = None) -> Result:
    """Extrude a sketch region. depth_mm is a number in millimetres.

    Workflow:
      1. Click the most recent sketch in the feature tree so the
         extrude tool knows which region to use. Required when the
         doc has more than one sketch.
      2. Activate the extrude tool (E or toolbar).
      3. Wait for the dialog. Find the depth input, clear it, type the
         value with "mm" unit, press Enter.
      4. Click the green checkmark to commit the feature.
    """
    depth_str = "default"
    # Step 1: pre-select the most recent sketch
    await _select_latest_sketch(d)

    # Step 2: activate extrude
    b = binding_for("feature.extrude")
    if b.keys:
        await d.press_chord(*b.keys)
    elif b.toolbar_text:
        clicked = await d.click_text(b.toolbar_text, timeout_ms=3000)
        if not clicked:
            return Result(False, f"feature.extrude: toolbar {b.toolbar_text!r} not found")
    else:
        return Result(False, "feature.extrude: no binding")
    await asyncio.sleep(0.5)  # dialog open animation

    if depth_mm is not None:
        # Step 3: fill the depth input. Onshape renders the depth field
        # as an input.os-canvas-text-edit. .fill() clears the field
        # first, then types the value with the unit suffix so Onshape
        # doesn't reinterpret it as the default unit (cm).
        depth_str = await _enter_value(d, parse_mm(depth_mm))

        # Step 4: commit with the green checkmark. No hardcoded-pixel
        # fallback — a guessed click here can cancel the feature instead.
        if not await _commit_dialog(d):
            shot = await d.screenshot("feature_extrude_failed.png")
            r = Result(False, "feature.extrude: commit button not found on the extrude dialog", shot)
            _record("feature.extrude", {"depth_mm": depth_mm}, r)
            return r
        # Some extrude paths need a second confirm. Shift+Enter
        # dismisses any tooltip without committing the wrong action.
        await d.press_chord("Shift", "Enter")
        await asyncio.sleep(0.5)

    shot = await d.screenshot("feature_extrude.png")
    meta = {"depth_mm": parse_mm(depth_mm)} if depth_mm is not None else {}
    r = Result(True, f"extrude depth={depth_str}", shot, meta)
    _record("feature.extrude", meta, r)
    return r


async def feature_revolve(d: OnshapeDriver, angle_deg: float = 360.0) -> Result:
    """Revolve the latest sketch region around an axis.

    Workflow:
      1. Click the most recent sketch in the feature tree.
      2. Activate revolve tool (toolbar 'Revolve' or Shift+W).
      3. In the Revolve dialog, select the axis (defaults to origin axis).
      4. Commit with the green checkmark.
    """
    await _select_latest_sketch(d)

    b = binding_for("feature.revolve")
    revolve_btn = d.page.locator("[command-id='revolve'], button[data-id='revolve']").first
    if await revolve_btn.count() > 0 and await revolve_btn.is_visible():
        await revolve_btn.click()
    elif b.toolbar_text and await d.click_text(b.toolbar_text, timeout_ms=2000):
        pass
    elif b.keys:
        await d.press_chord(*b.keys)
    else:
        await d.press_chord("Shift", "w")
    await asyncio.sleep(0.6)

    try:
        axis_field = d.page.locator(".parameter-entry, .ns-dialog-entry").filter(
            has_text=re.compile(r"Revolve axis|Axis", re.IGNORECASE)
        ).first
        if await axis_field.count() > 0:
            await axis_field.click()
            await asyncio.sleep(0.3)
    except Exception:
        pass

    try:
        vw = d.page.viewport_size or {"width": 1440, "height": 900}
        await d.click(vw["width"] / 2.0, vw["height"] / 2.0)
        await asyncio.sleep(0.3)
    except Exception:
        pass

    if not await _commit_dialog(d):
        shot = await d.screenshot("feature_revolve_failed.png")
        r = Result(False, "feature.revolve: commit button not found on the revolve dialog", shot)
        _record("feature.revolve", {"angle_deg": angle_deg}, r)
        return r
    await d.press_chord("Shift", "Enter")
    await asyncio.sleep(0.5)

    shot = await d.screenshot("feature_revolve.png")
    r = Result(True, f"revolve angle={angle_deg}deg", shot, {"angle_deg": angle_deg})
    _record("feature.revolve", {"angle_deg": angle_deg}, r)
    return r


async def feature_fillet(d: OnshapeDriver, radius_mm: float | None = None) -> Result:
    b = binding_for("feature.fillet")
    if b.toolbar_text:
        clicked = await d.click_text(b.toolbar_text, timeout_ms=3000)
        if not clicked and b.keys:
            await d.press_chord(*b.keys)
    elif b.keys:
        await d.press_chord(*b.keys)
    else:
        return Result(False, "feature.fillet: no binding")
    await asyncio.sleep(0.3)
    if radius_mm is not None:
        await d.type_text(str(radius_mm))
        await d.press_key("Enter")
        await asyncio.sleep(0.3)
    shot = await d.screenshot("feature_fillet.png")
    r = Result(True, f"fillet r={radius_mm}", shot)
    _record("feature.fillet", {"radius_mm": radius_mm}, r)
    return r


async def feature_chamfer(d: OnshapeDriver, distance_mm: float | None = None) -> Result:
    b = binding_for("feature.chamfer")
    if b.toolbar_text is None:
        return Result(False, "feature.chamfer: no binding")
    clicked = await d.click_text(b.toolbar_text, timeout_ms=3000)
    if not clicked:
        return Result(False, f"feature.chamfer: toolbar {b.toolbar_text!r} not found")
    await asyncio.sleep(0.3)
    if distance_mm is not None:
        await d.type_text(str(distance_mm))
        await d.press_key("Enter")
        await asyncio.sleep(0.3)
    shot = await d.screenshot("feature_chamfer.png")
    r = Result(True, f"chamfer d={distance_mm}", shot)
    _record("feature.chamfer", {"distance_mm": distance_mm}, r)
    return r


# Selection


async def select_face(d: OnshapeDriver, x: float, y: float) -> Result:
    """Click in the viewport to select a face. Best-effort: the face at
    that pixel may not be what was intended, so the LLM loop verifies via
    screenshot."""
    await d.click(x, y)
    await asyncio.sleep(0.2)
    shot = await d.screenshot("select_face.png")
    r = Result(True, f"clicked ({x},{y})", shot, {"click": [x, y]})
    _record("select.face", {"x": x, "y": y}, r)
    return r


async def select_edge(d: OnshapeDriver, x: float, y: float) -> Result:
    await d.click(x, y)
    await asyncio.sleep(0.2)
    shot = await d.screenshot("select_edge.png")
    r = Result(True, f"clicked edge ({x},{y})", shot, {"click": [x, y]})
    _record("select.edge", {"x": x, "y": y}, r)
    return r


# Global undo and redo


async def undo(d: OnshapeDriver) -> Result:
    b = binding_for("ui.undo")
    await d.press_chord(*b.keys)  # type: ignore[arg-type]
    await asyncio.sleep(0.2)
    shot = await d.screenshot("undo.png")
    r = Result(True, "undo", shot)
    _record("ui.undo", {}, r)
    return r


async def redo(d: OnshapeDriver) -> Result:
    b = binding_for("ui.redo")
    await d.press_chord(*b.keys)  # type: ignore[arg-type]
    await asyncio.sleep(0.2)
    shot = await d.screenshot("redo.png")
    r = Result(True, "redo", shot)
    _record("ui.redo", {}, r)
    return r


async def wait(d: OnshapeDriver, seconds: float = 1.0) -> Result:
    """No-op pause. Useful when the LLM wants to let a dialog animation
    finish, or just look at the current state again on the next step."""
    await asyncio.sleep(max(0.0, seconds))
    shot = await d.screenshot("wait.png")
    r = Result(True, f"waited {seconds}s", shot)
    _record("ui.wait", {"seconds": seconds}, r)
    return r


async def screenshot_only(d: OnshapeDriver, name: str = "agent.png") -> Result:
    """Bare screenshot without any other action. Lets the LLM re-observe
    the viewport without doing anything else."""
    shot = await d.screenshot(name)
    r = Result(True, f"screenshot {name}", shot)
    _record("screenshot", {"name": name}, r)
    return r


async def doc_open(d: OnshapeDriver, url: str) -> Result:
    """Navigate to a specific Onshape document URL. Pass either a full
    URL or a `d/<docId>/e/<elementId>` path. Usually elementId is a
    Part Studio — if the document has one, deep-link to it directly.
    """
    if not url:
        return Result(False, "doc.open: missing url")
    full = url if url.startswith("http") else f"https://cad.onshape.com/{url.lstrip('/')}"
    await d.open(full)
    shot = await d.screenshot("doc_open.png")
    r = Result(True, f"opened {full}", shot, {"url": full})
    _record("doc.open", {"url": full}, r)
    return r


async def doc_new(d: OnshapeDriver) -> Result:
    """Click the Onshape "Create" / new document button. Lands in a fresh
    Part Studio, which is where sketch + feature tools work.
    """
    try:
        if not await d.click_text("Create", timeout_ms=5000):
            return Result(False, "doc.new: 'Create' button not found on the documents page")
        await asyncio.sleep(0.5)
        if not await d.click_text("Document", timeout_ms=5000):
            return Result(False, "doc.new: 'Document' menu item not found under Create")
        await asyncio.sleep(1.0)
        await d.type_text("PartStudio")
        await asyncio.sleep(0.2)
        await d.press_key("Enter")
        await d.page.wait_for_url("**/documents/**/e/**", timeout=30000)
        await d.wait_for_app()
    except Exception as e:
        return Result(False, f"doc.new failed: {e}")
    shot = await d.screenshot("doc_new.png")
    r = Result(True, "new document", shot)
    _record("doc.new", {}, r)
    return r


async def feature_delete(d: OnshapeDriver, name: str) -> Result:
    """Delete a feature (e.g. 'Sketch 1', 'Extrude 1') from the Part Studio tree."""
    try:
        listing = await features_list(d)
        current_features = listing.meta.get("features", [])

        matching = [f for f in current_features if f.strip().lower() == name.strip().lower()]
        if not matching:
            shot = await d.screenshot(f"delete_{name.replace(' ', '_').lower()}.png")
            r = Result(True, f"Feature '{name}' is already absent from feature tree", shot)
            _record("feature.delete", {"name": name}, r)
            return r

        target_name = matching[0]

        label = d.page.locator(
            ".os-list-item.ns-user-feature span.os-list-item-name, span.os-list-item-name, .os-list-item-label"
        ).filter(has_text=re.compile(rf"^{re.escape(target_name)}$", re.IGNORECASE)).first
        if await label.count() == 0:
            label = d.page.locator("span.os-list-item-name, .os-list-item-label").filter(has_text=target_name).first

        if await label.count() == 0:
            return Result(True, f"Feature '{name}' is already absent from feature tree")

        try:
            await label.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            pass
        await asyncio.sleep(0.2)
        await label.click(button="right")
        await asyncio.sleep(0.4)

        delete_menu = d.page.locator(".os-context-menu-item, .dropdown-menu li, .context-menu-item").filter(has_text="Delete").last
        if await delete_menu.count() > 0 and await delete_menu.is_visible():
            await delete_menu.click()
        else:
            await d.press_key("Escape")
            await asyncio.sleep(0.2)
            await label.click()
            await asyncio.sleep(0.2)
            await d.press_key("Delete")

        confirm = d.page.get_by_role("button", name="Delete", exact=True).last
        if await confirm.count() > 0 and await confirm.is_visible():
            await confirm.click()

        await asyncio.sleep(0.8)
        shot = await d.screenshot(f"delete_{name.replace(' ', '_').lower()}.png")

        new_listing = await features_list(d)
        new_features = new_listing.meta.get("features", [])
        if any(f.strip().lower() == target_name.lower() for f in new_features):
            return Result(False, f"Delete command ran but feature '{target_name}' is still present", shot)
        r = Result(True, f"Deleted feature '{target_name}'", shot)
        _record("feature.delete", {"name": target_name}, r)
        return r
    except Exception as e:
        return Result(False, f"Failed deleting feature '{name}': {e}")


async def features_delete_all(d: OnshapeDriver) -> Result:
    """Delete all user features in the Part Studio tree."""
    try:
        listing = await features_list(d)
        names = listing.meta.get("features", [])
        if not names:
            return Result(True, "Feature tree is already empty (0 features)")
        deleted = []
        for name in reversed(names):
            res = await feature_delete(d, name)
            if res.ok:
                deleted.append(name)
        shot = await d.screenshot("delete_all.png")
        r = Result(True, f"Deleted {len(deleted)} feature(s): {', '.join(deleted)}", shot, {"deleted": deleted})
        _record("features.delete_all", {}, r)
        return r
    except Exception as e:
        return Result(False, f"Failed deleting all features: {e}")


async def feature_edit(d: OnshapeDriver, name: str) -> Result:
    """Open an existing feature or sketch (e.g. 'Sketch 1') for editing."""
    try:
        items = d.page.locator(".os-list-item.ns-user-feature, .os-list-item-label").filter(has_text=name)
        if await items.count() == 0:
            return Result(False, f"Feature '{name}' not found in feature tree")

        target = items.first
        await target.click(button="right")
        await asyncio.sleep(0.4)

        edit_btn = d.page.locator(".os-context-menu-item, .dropdown-menu li, .context-menu-item").filter(has_text="Edit…").first
        if await edit_btn.count() > 0:
            await edit_btn.click()
        else:
            await d.press_key("Escape")
            await asyncio.sleep(0.2)
            await target.dblclick()

        await asyncio.sleep(0.8)
        shot = await d.screenshot(f"edit_{name.replace(' ', '_').lower()}.png")
        r = Result(True, f"Opened feature '{name}' for editing", shot)
        _record("feature.edit", {"name": name}, r)
        return r
    except Exception as e:
        return Result(False, f"Failed editing feature '{name}': {e}")


async def features_list(d: OnshapeDriver) -> Result:
    """Return list of all features currently in the Part Studio tree."""
    try:
        js = """() => Array.from(document.querySelectorAll('.os-list-item.ns-user-feature span.os-list-item-name'))
            .map(n => n.innerText.trim())
            .filter(t => t.length > 0)"""
        names = await d.page.evaluate(js)
        shot = await d.screenshot("features_list.png")
        r = Result(True, f"Found {len(names)} features: {names}", shot, {"features": names})
        _record("features.list", {}, r)
        return r
    except Exception as e:
        return Result(False, f"Failed listing features: {e}")


async def doc_undo(d: OnshapeDriver) -> Result:
    """Undo the last action in Onshape."""
    try:
        await d.page.keyboard.press("Control+z")
        await asyncio.sleep(0.5)
        shot = await d.screenshot("doc_undo.png")
        r = Result(True, "Undo executed", shot)
        _record("doc.undo", {}, r)
        return r
    except Exception as e:
        return Result(False, f"Undo failed: {e}")


async def doc_redo(d: OnshapeDriver) -> Result:
    """Redo the last undone action in Onshape."""
    try:
        await d.page.keyboard.press("Control+y")
        await asyncio.sleep(0.5)
        shot = await d.screenshot("doc_redo.png")
        r = Result(True, "Redo executed", shot)
        _record("doc.redo", {}, r)
        return r
    except Exception as e:
        return Result(False, f"Redo failed: {e}")
