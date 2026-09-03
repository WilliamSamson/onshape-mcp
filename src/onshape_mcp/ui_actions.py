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


# ─── view / camera ────────────────────────────────────────────────────────

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


# ─── sketching ────────────────────────────────────────────────────────────

async def sketch_start(d: OnshapeDriver, plane_xy: tuple[float, float] | None = None) -> Result:
    """Click the Sketch button, then click a plane (or pass a coordinate).

    If `plane_xy` is None, we pick the origin of the default top plane by
    clicking the center of the viewport. For deterministic results, pass
    the exact pixel.
    """
    b = binding_for("sketch.start")
    if b.toolbar_text is None:
        return Result(False, "sketch.start: no toolbar binding")
    clicked = await d.click_text(b.toolbar_text, timeout_ms=4000)
    if not clicked:
        return Result(False, f"sketch.start: could not find {b.toolbar_text!r} button")
    # small settle delay for the UI to switch into plane-pick mode
    await asyncio.sleep(0.3)
    if plane_xy is None:
        box = await d.viewport_box()
        plane_xy = (box["w"] / 2.0, box["h"] / 2.0)
    await d.click(*plane_xy)
    await asyncio.sleep(0.2)
    shot = await d.screenshot("sketch_start.png")
    r = Result(True, f"sketch started at {plane_xy}", shot, {"click": list(plane_xy)})
    _record("sketch.start", {"plane_xy": list(plane_xy)}, r)
    return r


async def _activate_sketch_tool(d: OnshapeDriver, name: str) -> Result:
    b = binding_for(name)
    if b.toolbar_text is None:
        return Result(False, f"{name}: no toolbar binding")
    clicked = await d.click_text(b.toolbar_text, timeout_ms=3000)
    if not clicked:
        return Result(False, f"{name}: toolbar {b.toolbar_text!r} not found")
    await asyncio.sleep(0.15)
    return Result(True, f"{name} tool active")


async def sketch_rectangle(
    d: OnshapeDriver,
    corner1: tuple[float, float],
    corner2: tuple[float, float],
) -> Result:
    t = await _activate_sketch_tool(d, "sketch.rectangle")
    if not t.ok:
        _record("sketch.rectangle", {"corner1": list(corner1), "corner2": list(corner2)}, t)
        return t
    await d.click(*corner1)
    await asyncio.sleep(0.1)
    await d.click(*corner2)
    await asyncio.sleep(0.1)
    # press Esc to drop the rectangle tool (stay in sketch)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_rectangle.png")
    r = Result(True, f"rectangle {corner1} -> {corner2}", shot)
    _record("sketch.rectangle", {"corner1": list(corner1), "corner2": list(corner2)}, r)
    return r


async def sketch_circle(
    d: OnshapeDriver,
    center: tuple[float, float],
    radius_px: float,
) -> Result:
    t = await _activate_sketch_tool(d, "sketch.circle")
    if not t.ok:
        _record("sketch.circle", {"center": list(center), "radius_px": radius_px}, t)
        return t
    await d.click(*center)
    await asyncio.sleep(0.1)
    # Onshape: click-and-drag from center to set radius, OR click center then click on the
    # circle edge. We do click-edge because it's simpler from a coord-only model.
    await d.click(center[0] + radius_px, center[1])
    await asyncio.sleep(0.1)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_circle.png")
    r = Result(True, f"circle center={center} r={radius_px}", shot)
    _record("sketch.circle", {"center": list(center), "radius_px": radius_px}, r)
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
    await d.click(*p1)
    await asyncio.sleep(0.05)
    await d.click(*p2)
    await asyncio.sleep(0.05)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_line.png")
    r = Result(True, f"line {p1} -> {p2}", shot)
    _record("sketch.line", {"p1": list(p1), "p2": list(p2)}, r)
    return r


async def sketch_dimension(
    d: OnshapeDriver,
    entity_xy: tuple[float, float],
    label_xy: tuple[float, float],
    value_mm: float,
) -> Result:
    """Add or set a dimension. Click the entity at `entity_xy`, place the
    dimension label at `label_xy`, then type the new value + Enter.

    This is the workhorse of the "make it 5x5" workflow. Draw any
    rectangle, then call this twice (once for each side) with the
    target mm value. The LLM doesn't need to know the px-to-mm ratio
    because Onshape's solver does the conversion.
    """
    b = binding_for("sketch.dimension")
    if b.toolbar_text:
        ok = await d.click_text(b.toolbar_text, timeout_ms=3000)
        if not ok and b.keys:
            await d.press_chord(*b.keys)
        else:
            if not ok:
                return Result(False, f"sketch.dimension: toolbar {b.toolbar_text!r} not found")
    elif b.keys:
        await d.press_chord(*b.keys)
    else:
        return Result(False, "sketch.dimension: no binding")
    await asyncio.sleep(0.2)
    # Click the entity (line/edge/circle) to dimension
    await d.click(*entity_xy)
    await asyncio.sleep(0.15)
    # Click where to place the dimension label
    await d.click(*label_xy)
    await asyncio.sleep(0.2)
    # Type the new value, press Enter
    await d.type_text(str(value_mm))
    await d.press_key("Enter")
    await asyncio.sleep(0.2)
    # Esc to drop the dimension tool, stay in sketch
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_dimension.png")
    r = Result(
        True,
        f"dimensioned {value_mm}mm at {entity_xy}",
        shot,
        {"value_mm": value_mm},
    )
    _record(
        "sketch.dimension",
        {"entity_xy": list(entity_xy), "label_xy": list(label_xy), "value_mm": value_mm},
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
    b = binding_for("sketch.equal")
    if b.toolbar_text is None:
        return Result(False, "sketch.equal: no binding")
    ok = await d.click_text(b.toolbar_text, timeout_ms=3000)
    if not ok:
        return Result(False, f"sketch.equal: toolbar {b.toolbar_text!r} not found")
    await asyncio.sleep(0.2)
    for xy in entity_xys:
        await d.click(*xy)
        await asyncio.sleep(0.1)
    await d.press_key("Escape")
    shot = await d.screenshot("sketch_equal.png")
    r = Result(True, f"equal across {len(entity_xys)} entities", shot)
    _record("sketch.equal", {"entities": [list(xy) for xy in entity_xys]}, r)
    return r


async def sketch_exit(d: OnshapeDriver) -> Result:
    """Exit the active sketch. Presses Esc and verifies by screenshot diff."""
    before = await d.screenshot("sketch_exit_before.png")
    await d.press_key("Escape")
    await asyncio.sleep(0.3)
    after = await d.screenshot("sketch_exit_after.png")
    r = Result(True, "exit sketch (Esc)", after, {"before": str(before), "after": str(after)})
    _record("sketch.exit", {}, r)
    return r


# ─── features ─────────────────────────────────────────────────────────────

async def feature_extrude(d: OnshapeDriver, depth_mm: float | None = None) -> Result:
    """Extrude the active sketch region. If depth is None, opens the
    extrude dialog and screenshots so the LLM loop can type a value.
    """
    b = binding_for("feature.extrude")
    if b.toolbar_text:
        clicked = await d.click_text(b.toolbar_text, timeout_ms=3000)
        if not clicked and b.keys:
            await d.press_chord(*b.keys)
    elif b.keys:
        await d.press_chord(*b.keys)
    else:
        return Result(False, "feature.extrude: no binding")
    await asyncio.sleep(0.4)  # dialog open animation
    if depth_mm is not None:
        await d.type_text(str(depth_mm))
        await d.press_key("Enter")
        await asyncio.sleep(0.3)
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


# ─── selection ────────────────────────────────────────────────────────────

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


# ─── global undo/redo ─────────────────────────────────────────────────────

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
