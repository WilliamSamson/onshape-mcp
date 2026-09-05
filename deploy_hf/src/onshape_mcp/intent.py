"""Parse natural-language CAD prompts into structured action plans.

This module eliminates the LLM from deterministic tasks. Instead of
sending 4 screenshots to Gemini and waiting 60s for it to say
"sketch.start, sketch.rectangle, sketch.exit, done", we parse the
prompt directly and produce the same action sequence in <1ms.

If the parser can't handle a prompt, it returns None and the caller
falls back to the vision loop.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Action:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    actions: list[Action]
    summary: str


# Regex patterns for dimension extraction.
# Handles "12cm by 8cm", "12 cm x 8 cm", "50mm × 30mm" etc.
# Groups: (1)=width, (2)=width_unit, (3)=height, (4)=height_unit
_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|cm|in|inch)?\s*(?:x|by|×)\s*(\d+(?:\.\d+)?)\s*(mm|cm|in|inch)?",
    re.IGNORECASE,
)
_SINGLE_DIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|cm|in|inch)",
    re.IGNORECASE,
)
_PLANE_RE = re.compile(r"\b(top|front|right)\b", re.IGNORECASE)
_QUADRANT_RE = re.compile(
    r"(?:quadrant|q)\s*([1-4]|I{1,3}V?|IV)", re.IGNORECASE
)
_EXTRUDE_RE = re.compile(
    r"extrude\s+(?:it\s+)?(\d+(?:\.\d+)?)\s*(mm|cm|in)?", re.IGNORECASE
)
_DIAMETER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|cm|in)?\s*diameter", re.IGNORECASE
)
_RADIUS_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|cm|in)?\s*radius", re.IGNORECASE
)
_POLYGON_SIDES_RE = re.compile(
    r"(\d+)[ -]sided\b", re.IGNORECASE
)
_CENTERED_RE = re.compile(
    r"\b(center(?:ed)?|at\s+(?:the\s+)?origin)\b", re.IGNORECASE
)


def _format_dim(value: float, unit: str | None) -> str:
    """Format a dimension value with unit for Onshape's solver."""
    u = (unit or "cm").lower()
    if u in ("in", "inch"):
        u = "in"
    v = f"{value:g}"
    return f"{v} {u}"


def _extract_plane(text: str) -> str:
    m = _PLANE_RE.search(text)
    return m.group(1).capitalize() if m else "Top"


def _extract_quadrant(text: str) -> str | None:
    m = _QUADRANT_RE.search(text)
    if not m:
        return None
    q = m.group(1).upper()
    roman = {"I": "1", "II": "2", "III": "3", "IV": "4"}
    return roman.get(q, q)


def _is_centered(text: str) -> bool:
    return bool(_CENTERED_RE.search(text))


def parse(text: str) -> Plan | None:
    """Try to parse a natural-language CAD prompt into a deterministic
    action plan. Returns None if the prompt is too ambiguous or complex
    for direct execution.
    """
    t = text.strip()
    lower = t.lower()

    if not t:
        return None

    # Detect shape type
    is_rect = any(w in lower for w in ("box", "rectangle", "rect", "square"))
    is_circle = any(w in lower for w in ("circle", "cylinder", "disc", "disk"))
    is_polygon = any(w in lower for w in ("polygon", "hexagon", "pentagon", "octagon"))
    is_arc = "arc" in lower and not is_circle
    is_point = "point" in lower and not any((is_rect, is_circle, is_polygon, is_arc))
    has_extrude = "extrude" in lower

    if not (is_rect or is_circle or is_polygon or is_arc or is_point):
        return None

    plane = _extract_plane(t)
    quadrant = _extract_quadrant(t)
    centered = _is_centered(t)

    actions: list[Action] = []
    summary_parts: list[str] = []

    # Step 1: Start sketch
    actions.append(Action("sketch.start", {"plane": plane}))

    if is_rect:
        dim_m = _DIM_RE.search(t)
        if dim_m:
            w_val = float(dim_m.group(1))
            h_val = float(dim_m.group(3))
            unit = dim_m.group(2) or dim_m.group(4)
            width = _format_dim(w_val, unit)
            height = _format_dim(h_val, unit)
        elif "square" in lower:
            single = _SINGLE_DIM_RE.search(t)
            if single:
                val = float(single.group(1))
                unit = single.group(2)
                width = height = _format_dim(val, unit)
            else:
                return None
        else:
            return None

        rect_args: dict[str, Any] = {"width": width, "height": height}
        if quadrant:
            rect_args["quadrant"] = quadrant
        elif centered or not quadrant:
            rect_args["centered"] = True

        actions.append(Action("sketch.rectangle", rect_args))
        label = "square" if width == height else "rectangle"
        summary_parts.append(f"{width} × {height} {label}")

    elif is_circle:
        diam_m = _DIAMETER_RE.search(t)
        rad_m = _RADIUS_RE.search(t)
        if diam_m:
            val = float(diam_m.group(1))
            unit = diam_m.group(2)
            radius_mm = val / 2.0
            if unit and unit.lower() == "cm":
                radius_mm = val * 10.0 / 2.0
            circle_args: dict[str, Any] = {
                "centered": True,
                "radius": radius_mm,
            }
            actions.append(Action("sketch.circle", circle_args))
            summary_parts.append(f"{_format_dim(val, unit)} diameter circle")
        elif rad_m:
            val = float(rad_m.group(1))
            unit = rad_m.group(2)
            circle_args = {"centered": True, "radius": val}
            actions.append(Action("sketch.circle", circle_args))
            summary_parts.append(f"{_format_dim(val, unit)} radius circle")
        else:
            single = _SINGLE_DIM_RE.search(t)
            if single:
                val = float(single.group(1))
                unit = single.group(2)
                circle_args = {"centered": True, "radius": val / 2.0}
                actions.append(Action("sketch.circle", circle_args))
                summary_parts.append(f"{_format_dim(val, unit)} circle")
            else:
                return None

    elif is_polygon:
        # Determine number of sides
        sides = 6
        side_m = _POLYGON_SIDES_RE.search(t)
        if side_m:
            sides = int(side_m.group(1))
        elif "hexagon" in lower:
            sides = 6
        elif "pentagon" in lower:
            sides = 5
        elif "octagon" in lower:
            sides = 8

        # Determine radius
        rad_m = _RADIUS_RE.search(t) or _SINGLE_DIM_RE.search(t)
        radius_val = float(rad_m.group(1)) if rad_m else 50.0
        unit = rad_m.group(2) if rad_m else "mm"
        poly_args: dict[str, Any] = {
            "center_x": 0.0,
            "center_y": 0.0,
            "radius": radius_val,
            "sides": sides,
        }
        actions.append(Action("sketch.polygon", poly_args))
        summary_parts.append(f"{sides}-sided polygon (r={_format_dim(radius_val, unit)})")

    elif is_arc:
        arc_args: dict[str, Any] = {
            "p1_x": -50.0,
            "p1_y": 0.0,
            "p2_x": 50.0,
            "p2_y": 0.0,
        }
        actions.append(Action("sketch.arc", arc_args))
        summary_parts.append("3-point arc")

    elif is_point:
        actions.append(Action("sketch.point", {"x": 0.0, "y": 0.0}))
        summary_parts.append("point at origin")

    # Step: Exit sketch
    actions.append(Action("sketch.exit", {}))

    # Step: Extrude (optional)
    ext_m = _EXTRUDE_RE.search(t)
    if has_extrude and ext_m:
        depth_val = float(ext_m.group(1))
        depth_unit = (ext_m.group(2) or "mm").lower()
        if depth_unit == "cm":
            depth_mm = depth_val * 10.0
        elif depth_unit in ("in", "inch"):
            depth_mm = depth_val * 25.4
        else:
            depth_mm = depth_val
        actions.append(Action("feature.extrude", {"depth_mm": depth_mm}))
        summary_parts.append(f"extruded {_format_dim(depth_val, depth_unit)}")

    position = f"Quadrant {quadrant}" if quadrant else "centered at origin"
    summary = f"Drew {', '.join(summary_parts)} on {plane} plane, {position}"

    return Plan(actions=actions, summary=summary)
