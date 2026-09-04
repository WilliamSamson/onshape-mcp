"""High-level Onshape operations. Each public function corresponds to a
datasheet tool. Uses driver.py primitives + shortcuts.py bindings, journals
to journal.py. Raises before touching the UI if a precondition isn't met.

Conventions: every function takes the driver explicitly (no globals), returns
a `Result` dict, and uses viewport pixel coords. Call `driver.viewport_box()`
to get bounds.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .driver import OnshapeDriver
from .journal import JournalEntry, journal
from .shortcuts import get as binding_for


@dataclass
class Result:
    ok: bool
    note: str = ""
    screenshot: Path | None = None
    extra: dict[str, Any] | None = None

    @property
    def summary(self) -> str:
        return self.note

    @property
    def meta(self) -> dict[str, Any]:
        return self.extra or {}

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"ok": self.ok, "note": self.note}
        if self.screenshot is not None:
            d["screenshot"] = str(self.screenshot)
        if self.extra:
            d.update(self.extra)
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

# Sketching


async def sketch_start(
    d: OnshapeDriver,
    plane_xy: tuple[float, float] | None = None,
    plane_name: str | None = None,
) -> Result:
    """Click the Sketch button, then click a plane (or pass a coordinate/name).

    If `plane_xy` is None, we select the desired plane in the feature tree
    using DOM locator (default: Top plane) and press 'n' to orient normal to the sketch plane.
    """
    b = binding_for("sketch.start")
    if b.toolbar_text is None:
        return Result(False, "sketch.start: no toolbar binding")
    clicked = await d.click_text(b.toolbar_text, timeout_ms=2000)
    if not clicked:
        if b.keys:
            await d.press_chord(*b.keys)
        else:
            await d.click(155.0, 58.0)
    # small settle delay for the UI to switch into plane-pick mode
    await asyncio.sleep(0.4)

    target_name = (plane_name or "Top").capitalize()
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
            # Deterministically orient normal to the selected plane via context menu
            try:
                await loc.first.click(button="right")
                await asyncio.sleep(0.3)
                normal_item = d.page.locator(
                    "div.context-menu-item-text", has_text="View normal to"
                )
                if await normal_item.count() > 0:
                    await normal_item.first.click()
                else:
                    await d.press_key("n")
            except Exception:
                await d.press_key("n")
        else:
            await d.click(65.0, 232.0)
            await asyncio.sleep(0.4)
            await d.press_key("n")
    await asyncio.sleep(1.2)
    shot = await d.screenshot("sketch_start.png")
    r = Result(True, f"sketch started on {target_name}", shot, {"plane": target_name})
    _record("sketch.start", {"plane": target_name}, r)
    return r


SKETCH_COMMAND_IDS: dict[str, str] = {
    "sketch.rectangle": "RECTANGLE_TWO_CORNERS",
    "sketch.circle": "CIRCLE_CENTER_RADIUS",
    "sketch.line": "LINESEGMENT",
    "sketch.dimension": "DIMENSION",
    "sketch.equal": "EQUAL",
    "sketch.coincident": "COINCIDENT",
    "feature.extrude": "extrude",
    "feature.revolve": "revolve",
}


async def _activate_sketch_tool(d: OnshapeDriver, name: str) -> Result:
    cmd_id = SKETCH_COMMAND_IDS.get(name)
    if cmd_id:
        loc = d.page.locator(f"[command-id='{cmd_id}']")
        if await loc.count() > 0:
            classes = await loc.first.get_attribute("class") or ""
            if "is-active" in classes:
                return Result(True, f"{name} already active")
            await loc.first.click()
            await asyncio.sleep(0.3)
            return Result(True, f"{name} tool active (command-id: {cmd_id})")

    b = binding_for(name)
    if b.keys:
        await d.press_chord(*b.keys)
        await asyncio.sleep(0.2)
        return Result(True, f"{name} tool active (keys: {b.keys})")
    if b.toolbar_text:
        clicked = await d.click_text(b.toolbar_text, timeout_ms=3000)
        if clicked:
            await asyncio.sleep(0.15)
            return Result(True, f"{name} tool active")
    return Result(False, f"{name}: no binding available")


def _parse_dim_px(val: float | str | None, default_px: float = 120.0) -> float:
    if val is None:
        return default_px
    try:
        s = str(val).strip().lower()
        num = float("".join(c for c in s if c.isdigit() or c == "."))
        if "cm" in s:
            px = num * 32.583
        elif "mm" in s:
            px = num * 3.2583
        elif "in" in s or "inch" in s:
            px = num * 82.75
        elif num <= 25:
            px = num * 32.583
        else:
            px = num * 3.2583
        return max(40.0, min(550.0, px))
    except Exception:
        return default_px


async def get_canvas_origin(d: OnshapeDriver) -> tuple[float, float]:
    """Calculate the exact center point (origin) of the WebGL canvas.
    Takes into account the left feature panel (246px) and toolbar (76px).
    """
    try:
        box = await d.page.evaluate("""() => {
            const c = document.querySelector('canvas.os-main-canvas') || document.querySelector('canvas');
            if (!c) return {cx: 843.0, cy: 473.0};
            const r = c.getBoundingClientRect();
            return {cx: r.x + r.width / 2.0, cy: r.y + r.height / 2.0};
        }""")
        return (float(box.get("cx", 843.0)), float(box.get("cy", 473.0)))
    except Exception:
        return (843.0, 473.0)


async def _ensure_viewport_coords(d: OnshapeDriver, pt: tuple[float, float]) -> tuple[float, float]:
    x, y = pt
    cx, cy = await get_canvas_origin(d)
    # If pt is (0, 0), return exact origin
    if x == 0 and y == 0:
        return (cx, cy)
    # If small coordinates (CAD units relative to origin), convert to screen pixels:
    # In CAD space, +X is right, +Y is up (so screen Y is cy - y*scale)
    if abs(x) <= 200 and abs(y) <= 200:
        scale = 10.0 if (abs(x) <= 25 and abs(y) <= 25) else 1.0
        return (cx + x * scale, cy - y * scale)
    return (x, y)


async def sketch_rectangle(
    d: OnshapeDriver,
    corner1: tuple[float, float] | None = None,
    corner2: tuple[float, float] | None = None,
    width: float | str | None = None,
    height: float | str | None = None,
    quadrant: str | int | None = None,
    centered: bool | None = None,
) -> Result:
    cx, cy = await get_canvas_origin(d)
    span_x = _parse_dim_px(width, default_px=120.0)
    span_y = _parse_dim_px(height, default_px=120.0)

    if centered:
        corner1 = (cx - span_x / 2.0, cy - span_y / 2.0)
        corner2 = (cx + span_x / 2.0, cy + span_y / 2.0)
    elif quadrant is not None:
        q = str(quadrant).upper().strip()
        if q in ("1", "I", "TOP-RIGHT", "NE"):
            corner1 = (cx, cy)
            corner2 = (cx + span_x, cy - span_y)
        elif q in ("2", "II", "TOP-LEFT", "NW"):
            corner1 = (cx, cy)
            corner2 = (cx - span_x, cy - span_y)
        elif q in ("3", "III", "BOTTOM-LEFT", "SW"):
            corner1 = (cx, cy)
            corner2 = (cx - span_x, cy + span_y)
        elif q in ("4", "IV", "BOTTOM-RIGHT", "SE"):
            corner1 = (cx, cy)
            corner2 = (cx + span_x, cy + span_y)
    elif corner1 is None and corner2 is None:
        corner1 = (cx - span_x / 2.0, cy - span_y / 2.0)
        corner2 = (cx + span_x / 2.0, cy + span_y / 2.0)

    c1 = await _ensure_viewport_coords(
        d, corner1 if corner1 is not None else (cx - 70.0, cy - 70.0)
    )
    c2 = await _ensure_viewport_coords(
        d, corner2 if corner2 is not None else (cx + 70.0, cy + 70.0)
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

    # If width or height are specified, apply constraints and dimensions
    if width is not None and height is not None and str(width).strip() == str(height).strip():
        # Square: apply Equal constraint first so geometry is strictly equilateral
        await sketch_equal(d, top_pick, left_pick)
        await asyncio.sleep(0.5)
        # Dimension top edge
        await sketch_dimension(d, top_pick, top_label, width)
    elif width is not None:
        await sketch_dimension(d, top_pick, top_label, width)
        if height is not None:
            await asyncio.sleep(0.6)
            await sketch_dimension(d, left_pick, left_label, height)
    elif height is not None:
        await sketch_dimension(d, left_pick, left_label, height)

    shot = await d.screenshot("sketch_rectangle.png")
    meta = {
        "corner1": list(c1),
        "corner2": list(c2),
        "last_vertex": list(c2),
        "width": width,
        "height": height,
        "quadrant": quadrant,
        "centered": centered,
    }
    r = Result(True, f"rectangle {c1} -> {c2} (dim={width}x{height})", shot, meta)
    _record("sketch.rectangle", meta, r)
    return r


async def sketch_circle(
    d: OnshapeDriver,
    center: tuple[float, float] | None = None,
    radius_px: float = 50.0,
    centered: bool | None = None,
) -> Result:
    t = await _activate_sketch_tool(d, "sketch.circle")
    if not t.ok:
        _record(
            "sketch.circle", {"center": list(center) if center else None, "radius_px": radius_px}, t
        )
        return t
    cx, cy = await get_canvas_origin(d)
    if centered or center is None or center == (0, 0):
        c = (cx, cy)
    else:
        c = await _ensure_viewport_coords(d, center)
    r_px = radius_px if radius_px > 10 else radius_px * 15.0
    await d.click(*c)
    await asyncio.sleep(0.1)
    await d.click(c[0] + r_px, c[1])
    await asyncio.sleep(0.1)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_circle.png")
    r = Result(True, f"circle center={c} r={r_px}", shot)
    _record("sketch.circle", {"center": list(c), "radius_px": r_px}, r)
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
    # Type the new value into input.os-canvas-text-edit if present or directly
    val_str = f"{value_mm} mm" if isinstance(value_mm, (int, float)) else str(value_mm)
    dim_input = d.page.locator("input.os-canvas-text-edit")
    if await dim_input.count() > 0:
        await dim_input.first.fill(val_str)
        await asyncio.sleep(0.1)
        await d.page.keyboard.press("Enter")
        await asyncio.sleep(0.4)
    else:
        await d.type_text(val_str)
        await asyncio.sleep(0.1)
        await d.press_key("Enter")
        await asyncio.sleep(0.4)
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


async def sketch_exit(d: OnshapeDriver, commit: bool = True, **_kw) -> Result:
    """Exit and accept (or cancel) the active sketch."""
    before = await d.screenshot("sketch_exit_before.png")
    if commit:
        # Click green checkmark button on dialog
        ok_btn = d.page.locator(".ns-dialog-button-ok, .button-ok").first
        if await ok_btn.count() > 0:
            await ok_btn.click()
        else:
            await d.click(424.0, 93.0)
        await asyncio.sleep(0.5)
        await d.press_chord("Shift", "Enter")
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
    r = Result(
        True, "exit sketch", after, {"before": str(before), "after": str(after), "commit": commit}
    )
    _record("sketch.exit", {"commit": commit}, r)
    return r


# Feature tools


async def feature_extrude(d: OnshapeDriver, depth_mm: float | None = None) -> Result:
    """Extrude the active sketch region. If depth is None, opens the
    extrude dialog and screenshots so the LLM loop can type a value.
    """
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
        await d.type_text(str(depth_mm))
        await d.press_key("Enter")
        await asyncio.sleep(0.3)
        # Click green checkmark to commit feature
        await d.click(294.0, 105.0)
        await asyncio.sleep(0.3)
        await d.press_chord("Shift", "Enter")
        await asyncio.sleep(0.5)
    shot = await d.screenshot("feature_extrude.png")
    r = Result(True, f"extrude depth={depth_mm}", shot)
    _record("feature.extrude", {"depth_mm": depth_mm}, r)
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
        # Click Create dropdown button at top-left
        await d.click(75, 70)
        await asyncio.sleep(0.5)
        # Click "Document..." item
        await d.click(75, 110)
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
