"""Same-origin Onshape feature API helpers.

The MCP normally drives the UI, but deterministic parametric geometry should
not be inferred from pixels.  These helpers execute documented Feature API
requests inside the already authenticated Playwright page, so the browser's
Onshape session and XSRF protection are preserved without exporting cookies.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from .driver import OnshapeDriver

_DOC_RE = re.compile(r"/documents/([^/]+)/(w|v|m)/([^/]+)/e/([^/?#]+)")


def _message(value: dict[str, Any]) -> dict[str, Any]:
    message = value.get("message")
    return message if isinstance(message, dict) else value


def document_ref(url: str) -> tuple[str, str, str, str]:
    match = _DOC_RE.search(url)
    if not match:
        raise ValueError("Current page is not an Onshape Part Studio document URL")
    return match.group(1), match.group(2), match.group(3), match.group(4)


async def request(
    d: OnshapeDriver,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an authenticated same-origin API request and decode JSON."""
    result = await d.page.evaluate(
        """async ({method, path, payload}) => {
            const cookie = document.cookie.match(/(?:^|; )XSRF-TOKEN=([^;]+)/);
            const headers = {
                "Accept": "application/json;charset=UTF-8; qs=0.09",
                "Content-Type": "application/json;charset=UTF-8; qs=0.09",
            };
            if (cookie) headers["X-XSRF-TOKEN"] = decodeURIComponent(cookie[1]);
            const response = await fetch(path, {
                method,
                credentials: "include",
                headers,
                body: payload == null ? undefined : JSON.stringify(payload),
            });
            return {status: response.status, text: await response.text()};
        }""",
        {"method": method.upper(), "path": path, "payload": payload},
    )
    status = int(result.get("status", 0))
    text = str(result.get("text", ""))
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        data = {"raw": text[:1000]}
    if not 200 <= status < 300:
        raise RuntimeError(f"Onshape API {method.upper()} {path} returned HTTP {status}: {data}")
    return data


def _segment(entity_id: str, start: tuple[float, float], end: tuple[float, float]) -> dict[str, Any]:
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length <= 0:
        raise ValueError(f"zero-length segment: {entity_id}")
    return {
        "btType": "BTMSketchCurveSegment-155",
        "startPointId": f"{entity_id}.start",
        "endPointId": f"{entity_id}.end",
        "startParam": -length / 2.0,
        "endParam": length / 2.0,
        "geometry": {
            "btType": "BTCurveGeometryLine-117",
            "pntX": (x1 + x2) / 2.0,
            "pntY": (y1 + y2) / 2.0,
            "dirX": dx / length,
            "dirY": dy / length,
        },
        "isConstruction": False,
        "entityId": entity_id,
    }


def _circle(entity_id: str, center: tuple[float, float], radius: float) -> dict[str, Any]:
    if radius <= 0:
        raise ValueError(f"circle {entity_id}: radius must be positive")
    return {
        "btType": "BTMSketchCurve-4",
        "geometry": {
            "btType": "BTCurveGeometryCircle-115",
            "radius": radius,
            "xCenter": center[0],
            "yCenter": center[1],
            "xDir": 1.0,
            "yDir": 0.0,
            "clockwise": False,
        },
        "centerId": f"{entity_id}.center",
        "isConstruction": False,
        "entityId": entity_id,
    }


PLANE_QUERY = 'query=qCreatedBy(makeId("{plane}"), EntityType.FACE);'


def _mm(v: float) -> float:
    """Onshape's API works in metres; every public argument here is mm."""
    return float(v) / 1000.0


def sketch_payload(
    plane: str,
    shapes: list[dict[str, Any]],
    name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a sketch whose geometry is exact by construction.

    The UI path has to draw at some pixel scale and then argue the true
    size back in through the dimension solver, which fails for anything
    small enough that the drawn shape gets clamped. Here the coordinates
    ARE the geometry, so zoom, canvas size and clamping cannot affect it.

    Coordinates and sizes are millimetres, matching every other tool.
    """
    entities: list[dict[str, Any]] = []
    expected: dict[str, Any] = {}

    def add_segment(eid: str, p1: tuple[float, float], p2: tuple[float, float]) -> None:
        entities.append(_segment(eid, (_mm(p1[0]), _mm(p1[1])), (_mm(p2[0]), _mm(p2[1]))))
        expected[eid] = {"kind": "segment", "start_mm": list(p1), "end_mm": list(p2)}

    for i, s in enumerate(shapes):
        stype = str(s.get("type", "")).lower().strip()
        cx = float(s.get("center_x", 0.0))
        cy = float(s.get("center_y", 0.0))

        if stype in ("circle", "hole"):
            dia = s.get("diameter_mm", s.get("diameter"))
            r_mm = float(dia) / 2.0 if dia is not None else float(
                s.get("radius_mm", s.get("radius", 5.0))
            )
            eid = f"s{i}.circle"
            entities.append(_circle(eid, (_mm(cx), _mm(cy)), _mm(r_mm)))
            expected[eid] = {"kind": "circle", "center_mm": [cx, cy], "radius_mm": r_mm}

        elif stype in ("rectangle", "box", "square"):
            w = float(s.get("width_mm", s.get("width", 50.0)))
            h = float(s.get("height_mm", s.get("height", w)))
            if s.get("centered", True):
                x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
            else:
                x0, y0, x1, y1 = cx, cy, cx + w, cy + h
            corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            for k in range(4):
                add_segment(f"s{i}.side{k}", corners[k], corners[(k + 1) % 4])

        elif stype in ("polygon", "hexagon", "hex", "pentagon", "octagon", "triangle"):
            sides = int(s.get("sides", {"triangle": 3, "pentagon": 5, "octagon": 8}.get(stype, 6)))
            if sides < 3:
                raise ValueError(f"polygon needs at least 3 sides, got {sides}")
            r_mm = float(s.get("radius_mm", s.get("radius", 25.0)))
            if s.get("across_flats_mm") is not None:
                # Spanner size: the inscribed-circle diameter, which is how
                # fastener heads are actually specified.
                r_mm = float(s["across_flats_mm"]) / 2.0 / math.cos(math.pi / sides)
            rot = math.radians(float(s.get("rotation_deg", 0.0)))
            pts = [
                (
                    cx + r_mm * math.cos(rot + 2 * math.pi * k / sides),
                    cy + r_mm * math.sin(rot + 2 * math.pi * k / sides),
                )
                for k in range(sides)
            ]
            for k in range(sides):
                add_segment(f"s{i}.edge{k}", pts[k], pts[(k + 1) % sides])

        elif stype in ("line", "segment"):
            p1 = s.get("p1", (0.0, 0.0))
            p2 = s.get("p2", (10.0, 0.0))
            add_segment(f"s{i}.line", (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1])))

        elif stype in ("lines", "polyline", "path", "profile"):
            pts = [(float(p[0]), float(p[1])) for p in s.get("points", [])]
            if len(pts) < 2:
                raise ValueError(f"{stype} needs at least 2 points")
            if s.get("closed"):
                pts.append(pts[0])
            for k in range(len(pts) - 1):
                add_segment(f"s{i}.seg{k}", pts[k], pts[k + 1])

        else:
            raise ValueError(f"unsupported shape type {stype!r} for exact sketching")

    if not entities:
        raise ValueError("no shapes given")

    payload = {
        "btType": "BTFeatureDefinitionCall-1406",
        "feature": {
            "btType": "BTMSketch-151",
            "featureType": "newSketch",
            "name": name,
            "parameters": [
                {
                    "btType": "BTMParameterQueryList-148",
                    "queries": [
                        {
                            "btType": "BTMIndividualQuery-138",
                            "queryString": PLANE_QUERY.format(plane=plane.capitalize()),
                        }
                    ],
                    "parameterId": "sketchPlane",
                }
            ],
            "entities": entities,
            "constraints": [],
            "suppressed": False,
        },
    }
    return payload, expected


def verify_sketch_feature(
    feature: dict[str, Any], expected: dict[str, Any], tolerance_mm: float = 1e-4
) -> dict[str, Any]:
    """Read the geometry back out of Onshape and compare it to the request.

    Reporting what was asked for is not evidence. This reports what
    Onshape actually stored.
    """
    feature = _message(feature)
    entities = {_message(e).get("entityId"): e for e in feature.get("entities", [])}
    errors: list[str] = []
    measured: dict[str, Any] = {}

    for eid, want in expected.items():
        ent = entities.get(eid)
        if ent is None:
            errors.append(f"missing entity {eid}")
            continue
        if want["kind"] == "circle":
            geom = _message(_message(ent)["geometry"])
            r_mm = float(geom["radius"]) * 1000.0
            c_mm = [float(geom["xCenter"]) * 1000.0, float(geom["yCenter"]) * 1000.0]
            measured[eid] = {"radius_mm": round(r_mm, 6), "center_mm": [round(v, 6) for v in c_mm]}
            if abs(r_mm - want["radius_mm"]) > tolerance_mm:
                errors.append(f"{eid}: radius {r_mm:.4f}mm != requested {want['radius_mm']}mm")
            if math.dist(c_mm, want["center_mm"]) > tolerance_mm:
                errors.append(f"{eid}: centre moved")
        else:
            (sx, sy), (ex, ey) = _segment_endpoints(ent)
            s_mm, e_mm = [sx * 1000.0, sy * 1000.0], [ex * 1000.0, ey * 1000.0]
            measured[eid] = {
                "start_mm": [round(v, 6) for v in s_mm],
                "end_mm": [round(v, 6) for v in e_mm],
                "length_mm": round(math.dist(s_mm, e_mm), 6),
            }
            if math.dist(s_mm, want["start_mm"]) > tolerance_mm or math.dist(
                e_mm, want["end_mm"]
            ) > tolerance_mm:
                errors.append(f"{eid}: endpoints differ from request")

    return {
        "ok": not errors,
        "name": feature.get("name"),
        "feature_id": feature.get("featureId"),
        "entity_count": len(entities),
        "geometry": measured,
        "errors": errors,
    }


async def create_exact_sketch(
    d: OnshapeDriver,
    plane: str = "Top",
    shapes: list[dict[str, Any]] | None = None,
    name: str = "Exact Sketch",
) -> dict[str, Any]:
    """Create a sketch through the Feature API and verify it by reading back."""
    did, wvm, wvmid, eid = document_ref(d.page.url)
    if wvm != "w":
        raise ValueError("Creating features requires a writable Onshape workspace URL")
    payload, expected = sketch_payload(plane, shapes or [], name)
    base = f"/api/v9/partstudios/d/{did}/w/{wvmid}/e/{eid}/features"
    created = await request(d, "POST", base, payload)
    state = _message(created.get("featureState", {})).get("featureStatus")
    feature_id = _feature_id(created)
    listing = await request(
        d, "GET", base + "?rollbackBarIndex=-1&includeGeometryIds=true&noSketchGeometry=false"
    )
    feature = next(
        (
            f
            for f in reversed(listing.get("features", []))
            if (feature_id and _message(f).get("featureId") == feature_id)
            or _message(f).get("name") == name
        ),
        None,
    )
    if feature is None:
        raise RuntimeError("Onshape accepted the sketch but it was absent from the feature list")
    verified = verify_sketch_feature(feature, expected)
    verified["feature_status"] = state
    verified["plane"] = plane.capitalize()
    if state not in (None, "OK"):
        verified["ok"] = False
        verified["errors"].append(f"Onshape feature status is {state}")
    await d.page.reload(wait_until="load", timeout=60_000)
    await d.wait_for_app()
    return verified


def m4_profile_payload(
    *,
    length_mm: float = 20.0,
    shank_diameter_mm: float = 4.0,
    head_diameter_mm: float = 7.0,
    head_height_mm: float = 4.0,
    name: str = "M4x20 Exact Profile",
) -> tuple[dict[str, Any], dict[str, tuple[tuple[float, float], tuple[float, float]]]]:
    """Build one closed half-section whose lower boundary is the revolve axis."""
    if min(length_mm, shank_diameter_mm, head_diameter_mm, head_height_mm) <= 0:
        raise ValueError("M4 profile dimensions must be positive")
    shaft_r = shank_diameter_mm / 2.0 / 1000.0
    head_r = head_diameter_mm / 2.0 / 1000.0
    length = length_mm / 1000.0
    head_h = head_height_mm / 1000.0

    expected = {
        "m4.headAxis": ((-head_h, 0.0), (0.0, 0.0)),
        "m4.shaftAxis": ((0.0, 0.0), (length, 0.0)),
        "m4.tip": ((length, 0.0), (length, shaft_r)),
        "m4.shaftTop": ((length, shaft_r), (0.0, shaft_r)),
        "m4.shoulder": ((0.0, shaft_r), (0.0, head_r)),
        "m4.headTop": ((0.0, head_r), (-head_h, head_r)),
        "m4.headOuter": ((-head_h, head_r), (-head_h, 0.0)),
    }
    payload = {
        "btType": "BTFeatureDefinitionCall-1406",
        "feature": {
            "btType": "BTMSketch-151",
            "featureType": "newSketch",
            "name": name,
            "parameters": [
                {
                    "btType": "BTMParameterQueryList-148",
                    "queries": [
                        {
                            "btType": "BTMIndividualQuery-138",
                            "queryString": 'query=qCreatedBy(makeId("Front"), EntityType.FACE);',
                        }
                    ],
                    "parameterId": "sketchPlane",
                }
            ],
            "entities": [_segment(entity_id, *points) for entity_id, points in expected.items()],
            "constraints": [],
            "suppressed": False,
        },
    }
    return payload, expected


def _feature_id(response: dict[str, Any]) -> str | None:
    feature = response.get("feature")
    if isinstance(feature, dict):
        return _message(feature).get("featureId")
    return None


def _segment_endpoints(entity: dict[str, Any]) -> tuple[tuple[float, float], tuple[float, float]]:
    entity = _message(entity)
    geometry = _message(entity["geometry"])
    px, py = float(geometry["pntX"]), float(geometry["pntY"])
    dx, dy = float(geometry["dirX"]), float(geometry["dirY"])
    start, end = float(entity["startParam"]), float(entity["endParam"])
    return ((px + dx * start, py + dy * start), (px + dx * end, py + dy * end))


def verify_profile_feature(
    feature: dict[str, Any],
    expected: dict[str, tuple[tuple[float, float], tuple[float, float]]],
    tolerance_m: float = 1e-8,
) -> dict[str, Any]:
    feature = _message(feature)
    entities = {_message(e).get("entityId"): e for e in feature.get("entities", [])}
    errors: list[str] = []
    measured: dict[str, dict[str, Any]] = {}
    for entity_id, wanted in expected.items():
        entity = entities.get(entity_id)
        if entity is None:
            errors.append(f"missing segment {entity_id}")
            continue
        actual = _segment_endpoints(entity)
        for index in range(2):
            if math.dist(actual[index], wanted[index]) > tolerance_m:
                errors.append(f"{entity_id} endpoint {index} differs from requested coordinates")
        measured[entity_id] = {
            "start_mm": [round(v * 1000.0, 6) for v in actual[0]],
            "end_mm": [round(v * 1000.0, 6) for v in actual[1]],
            "length_mm": round(math.dist(*actual) * 1000.0, 6),
        }
    if len(entities) != len(expected):
        errors.append(f"expected {len(expected)} entities, found {len(entities)}")
    return {
        "ok": not errors,
        "name": feature.get("name"),
        "feature_id": feature.get("featureId"),
        "entity_count": len(entities),
        "closed": not errors,
        "segments": measured,
        "errors": errors,
    }


async def create_m4_profile(
    d: OnshapeDriver,
    *,
    length_mm: float = 20.0,
    name: str = "M4x20 Exact Profile",
) -> dict[str, Any]:
    did, wvm, wvmid, eid = document_ref(d.page.url)
    if wvm != "w":
        raise ValueError("Creating features requires a writable Onshape workspace URL")
    payload, expected = m4_profile_payload(length_mm=length_mm, name=name)
    base = f"/api/v9/partstudios/d/{did}/w/{wvmid}/e/{eid}/features"
    created = await request(d, "POST", base, payload)
    state = _message(created.get("featureState", {})).get("featureStatus")
    feature_id = _feature_id(created)
    listing = await request(
        d,
        "GET",
        base + "?rollbackBarIndex=-1&includeGeometryIds=true&noSketchGeometry=false",
    )
    candidates = listing.get("features", [])
    feature = next(
        (
            f
            for f in reversed(candidates)
            if (feature_id and _message(f).get("featureId") == feature_id)
            or _message(f).get("name") == name
        ),
        None,
    )
    if feature is None:
        raise RuntimeError("Onshape accepted the profile but it was absent from the feature list")
    verified = verify_profile_feature(feature, expected)
    verified["feature_status"] = state
    verified["api_status"] = "created"
    verified["requested"] = {
        "standard": "M4 coarse",
        "pitch_mm": 0.7,
        "length_mm": length_mm,
        "shank_diameter_mm": 4.0,
        "head_diameter_mm": 7.0,
        "head_height_mm": 4.0,
        "plane": "Front",
        "revolve_axis": "y=0 horizontal axis",
    }
    if state not in (None, "OK"):
        verified["ok"] = False
        verified["errors"].append(f"Onshape feature status is {state}")
    await d.page.reload(wait_until="load", timeout=60_000)
    await d.wait_for_app()
    return verified
