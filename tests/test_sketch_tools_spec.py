"""Test all sketch tools, bindings, dispatch registrations, and intent parsing."""

import pytest

from onshape_mcp import dispatch, shortcuts, tools
from onshape_mcp.intent import parse


class TestSketchToolRegistry:
    def test_all_sketch_tools_have_bindings(self):
        """Every sketch tool defined in tools.py must have a binding in shortcuts.py."""
        sketch_tools = [t for t in tools.ALL_TOOLS if t.name.startswith("sketch.") or t.name.startswith("constraint.")]
        for t in sketch_tools:
            b = shortcuts.get(t.name)
            assert b is not None, f"Missing binding for {t.name}"

    def test_all_sketch_tools_in_dispatch(self):
        """Every sketch tool and constraint must be mapped in dispatch.TOOL_DISPATCH."""
        sketch_tools = [t for t in tools.ALL_TOOLS if t.name.startswith("sketch.") or t.name.startswith("constraint.")]
        for t in sketch_tools:
            assert t.name in dispatch.TOOL_DISPATCH, f"Missing dispatch handler for {t.name}"

    def test_constraints_mapped(self):
        expected_constraints = [
            "constraint.coincident",
            "constraint.concentric",
            "constraint.parallel",
            "constraint.tangent",
            "constraint.horizontal",
            "constraint.vertical",
            "constraint.perpendicular",
            "constraint.equal",
            "constraint.midpoint",
            "constraint.fix",
        ]
        for c in expected_constraints:
            assert c in dispatch.TOOL_DISPATCH
            assert shortcuts.get(c) is not None


class TestPolygonIntentParsing:
    def test_hexagon(self):
        plan = parse("draw a 6-sided polygon with 40mm radius on the top plane")
        assert plan is not None
        assert plan.actions[0].tool == "sketch.start"
        assert plan.actions[1].tool == "sketch.polygon"
        assert plan.actions[1].args["sides"] == 6
        assert plan.actions[1].args["radius"] == 40.0
        assert plan.actions[2].tool == "sketch.exit"

    def test_named_polygons(self):
        p_hex = parse("draw a hexagon on the front plane")
        assert p_hex is not None
        assert p_hex.actions[1].args["sides"] == 6

        p_oct = parse("draw an 8-sided polygon on the top plane")
        assert p_oct is not None
        assert p_oct.actions[1].args["sides"] == 8

    def test_polygon_with_extrude(self):
        plan = parse("draw a 6-sided polygon with 50mm radius on the top plane and extrude it 25mm")
        assert plan is not None
        assert len(plan.actions) == 4
        assert plan.actions[1].tool == "sketch.polygon"
        assert plan.actions[2].tool == "sketch.exit"
        assert plan.actions[3].tool == "feature.extrude"
        assert plan.actions[3].args["depth_mm"] == 25.0


class TestArcAndPointIntent:
    def test_arc(self):
        plan = parse("draw a 3-point arc on the top plane")
        assert plan is not None
        assert plan.actions[1].tool == "sketch.arc"

    def test_point(self):
        plan = parse("place a point at the origin on the front plane")
        assert plan is not None
        assert plan.actions[1].tool == "sketch.point"
