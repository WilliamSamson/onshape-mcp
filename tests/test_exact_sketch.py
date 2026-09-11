"""Exact sketch geometry, built for the Feature API.

The click-based path could not size small parts: a 9.5mm circle was drawn
at the 30px floor and Onshape stored 24.889mm. These are pure geometry
checks — no browser, no network.
"""

import math

import pytest

from onshape_mcp.onshape_api import sketch_payload, verify_sketch_feature


def _entities(payload):
    return {e["entityId"]: e for e in payload["feature"]["entities"]}


def test_circle_is_exact_and_in_metres():
    payload, expected = sketch_payload("Right", [{"type": "circle", "diameter_mm": 9.5}], "t")
    geom = _entities(payload)["s0.circle"]["geometry"]
    assert geom["radius"] == pytest.approx(0.00475)  # 4.75mm in metres
    assert expected["s0.circle"]["radius_mm"] == pytest.approx(4.75)


def test_small_circle_is_not_clamped():
    """The whole point: 1mm stays 1mm."""
    payload, _ = sketch_payload("Top", [{"type": "circle", "radius_mm": 0.5}], "t")
    assert _entities(payload)["s0.circle"]["geometry"]["radius"] == pytest.approx(0.0005)


def test_hex_across_flats_matches_spanner_size():
    """across_flats is how fastener heads are specified, not circumradius."""
    _, expected = sketch_payload(
        "Right", [{"type": "polygon", "sides": 6, "across_flats_mm": 8}], "t"
    )
    ys = [p["start_mm"][1] for p in expected.values()]
    assert max(ys) == pytest.approx(4.0)
    assert min(ys) == pytest.approx(-4.0)
    circumradius = max(math.hypot(*p["start_mm"]) for p in expected.values())
    assert circumradius == pytest.approx(4.0 / math.cos(math.pi / 6))


def test_rectangle_is_four_closed_sides():
    _, expected = sketch_payload(
        "Top", [{"type": "rectangle", "width_mm": 50, "height_mm": 30}], "t"
    )
    assert len(expected) == 4
    lengths = sorted(round(math.dist(e["start_mm"], e["end_mm"]), 6) for e in expected.values())
    assert lengths == [30.0, 30.0, 50.0, 50.0]
    # each corner is shared by exactly two sides
    starts = {tuple(e["start_mm"]) for e in expected.values()}
    ends = {tuple(e["end_mm"]) for e in expected.values()}
    assert starts == ends


def test_plane_goes_into_the_query():
    payload, _ = sketch_payload("front", [{"type": "circle", "radius_mm": 1}], "t")
    q = payload["feature"]["parameters"][0]["queries"][0]["queryString"]
    assert 'makeId("Front")' in q


def test_verify_catches_geometry_that_came_back_wrong():
    """A size must be reported from what Onshape stored, not what we asked."""
    _, expected = sketch_payload("Top", [{"type": "circle", "radius_mm": 4.75}], "t")
    wrong = {
        "entities": [
            {
                "entityId": "s0.circle",
                "geometry": {
                    "btType": "BTCurveGeometryCircle-115",
                    "radius": 0.0124445,  # the 24.889mm diameter we actually got
                    "xCenter": 0.0,
                    "yCenter": 0.0,
                },
            }
        ]
    }
    res = verify_sketch_feature(wrong, expected)
    assert res["ok"] is False
    assert "radius" in res["errors"][0]


def test_unsupported_shape_is_rejected_not_ignored():
    with pytest.raises(ValueError, match="unsupported shape"):
        sketch_payload("Top", [{"type": "spline", "points": [[0, 0], [1, 1]]}], "t")
