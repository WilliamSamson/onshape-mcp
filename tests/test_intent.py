"""Tests for the intent parser (no LLM, no Onshape, pure logic)."""

import pytest

from onshape_mcp.intent import Plan, parse


class TestRectangle:
    def test_basic_box_cm(self):
        plan = parse("Create a sketch and draw a 12cm by 8cm box on the front plane")
        assert plan is not None
        assert len(plan.actions) == 3
        assert plan.actions[0].tool == "sketch.start"
        assert plan.actions[0].args["plane"] == "Front"
        assert plan.actions[1].tool == "sketch.rectangle"
        assert plan.actions[1].args["width"] == "12 cm"
        assert plan.actions[1].args["height"] == "8 cm"
        assert plan.actions[2].tool == "sketch.exit"

    def test_box_with_quadrant(self):
        plan = parse("draw a 10cm by 5cm box in Quadrant 1 on the top plane")
        assert plan is not None
        assert plan.actions[1].args["quadrant"] == "1"
        assert plan.actions[1].args.get("centered") is None

    def test_box_mm(self):
        plan = parse("draw a 50mm by 30mm rectangle on the right plane")
        assert plan is not None
        assert plan.actions[0].args["plane"] == "Right"
        assert plan.actions[1].args["width"] == "50 mm"
        assert plan.actions[1].args["height"] == "30 mm"

    def test_box_inches(self):
        plan = parse("draw a 2in by 1in box on the top plane")
        assert plan is not None
        assert plan.actions[1].args["width"] == "2 in"
        assert plan.actions[1].args["height"] == "1 in"

    def test_centered_explicit(self):
        plan = parse("draw a centered 5cm by 5cm rectangle on the top plane")
        assert plan is not None
        assert plan.actions[1].args.get("centered") is True

    def test_at_origin(self):
        plan = parse("draw a 10cm by 10cm box at the origin on the front plane")
        assert plan is not None
        assert plan.actions[1].args.get("centered") is True

    def test_default_plane_is_top(self):
        plan = parse("draw a 10cm by 5cm box")
        assert plan is not None
        assert plan.actions[0].args["plane"] == "Top"

    def test_centered_default_no_quadrant(self):
        plan = parse("draw a 10cm by 5cm box on the top plane")
        assert plan is not None
        assert plan.actions[1].args.get("centered") is True
        assert plan.actions[1].args.get("quadrant") is None

    def test_decimal_dims(self):
        plan = parse("draw a 12.5cm by 8.75cm rectangle on the front plane")
        assert plan is not None
        assert plan.actions[1].args["width"] == "12.5 cm"
        assert plan.actions[1].args["height"] == "8.75 cm"

    def test_quadrant_roman(self):
        plan = parse("draw a 10cm by 5cm box in Quadrant III on the top plane")
        assert plan is not None
        assert plan.actions[1].args["quadrant"] == "3"

    def test_square_shorthand(self):
        plan = parse("draw a 5cm square on the top plane")
        assert plan is not None
        assert plan.actions[1].args["width"] == "5 cm"
        assert plan.actions[1].args["height"] == "5 cm"


class TestWithExtrude:
    def test_box_plus_extrude(self):
        plan = parse("draw a 10cm by 5cm box on the top plane and extrude it 20mm")
        assert plan is not None
        assert len(plan.actions) == 4
        assert plan.actions[2].tool == "sketch.exit"
        assert plan.actions[3].tool == "feature.extrude"
        assert plan.actions[3].args["depth_mm"] == 20.0

    def test_extrude_cm(self):
        plan = parse("draw a 5cm by 5cm square on the top plane, extrude 2cm")
        assert plan is not None
        assert plan.actions[3].args["depth_mm"] == 20.0  # 2cm = 20mm


class TestCircle:
    def test_circle_diameter(self):
        plan = parse("draw a 50mm diameter circle on the top plane")
        assert plan is not None
        assert plan.actions[1].tool == "sketch.circle"
        assert plan.actions[1].args["centered"] is True

    def test_circle_radius(self):
        plan = parse("draw a 25mm radius circle on the front plane")
        assert plan is not None
        assert plan.actions[1].tool == "sketch.circle"
        assert plan.actions[0].args["plane"] == "Front"


class TestFallback:
    def test_ambiguous_prompt_returns_none(self):
        assert parse("make the part look good") is None

    def test_empty_prompt(self):
        assert parse("") is None

    def test_text_only_prompt(self):
        assert parse("I need help with my project") is None


class TestPolygon:
    def test_hexagon(self):
        plan = parse("draw a 6-sided polygon on the top plane")
        assert plan is not None
        assert plan.actions[1].tool == "sketch.polygon"
        assert plan.actions[1].args["sides"] == 6

    def test_octagon_extrude(self):
        plan = parse("draw an 8-sided polygon with 30mm radius on the front plane and extrude it 10mm")
        assert plan is not None
        assert plan.actions[1].args["sides"] == 8
        assert plan.actions[3].tool == "feature.extrude"
        assert plan.actions[3].args["depth_mm"] == 10.0


class TestArcAndPoint:
    def test_arc(self):
        plan = parse("draw a 3-point arc on the top plane")
        assert plan is not None
        assert plan.actions[1].tool == "sketch.arc"

    def test_point(self):
        plan = parse("draw a point at the origin on the top plane")
        assert plan is not None
        assert plan.actions[1].tool == "sketch.point"


class TestPlanStructure:
    def test_summary_includes_dimensions(self):
        plan = parse("draw a 10cm by 5cm box on the front plane")
        assert plan is not None
        assert "10 cm" in plan.summary
        assert "5 cm" in plan.summary
        assert "Front" in plan.summary

    def test_actions_are_ordered(self):
        plan = parse("draw a 10cm by 5cm box on the top plane and extrude 10mm")
        assert plan is not None
        tools = [a.tool for a in plan.actions]
        assert tools == ["sketch.start", "sketch.rectangle", "sketch.exit", "feature.extrude"]
