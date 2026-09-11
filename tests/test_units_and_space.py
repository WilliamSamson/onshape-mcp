"""Units and coordinate-space handling.

These two used to be inferred from magnitude ("a number under 25 is
probably cm", "a coordinate over 250 is probably pixels"), which turned
a wrong guess into a wrong part with no error. Lock the explicit
behaviour in.
"""

import asyncio

from onshape_mcp.ui_actions import COORD_SPACE, _ensure_viewport_coords, parse_mm


class DummyDriver:
    """Canvas 1200x900 centred at (843, 473)."""

    @property
    def page(self):
        class DummyPage:
            async def evaluate(self, script):
                if "height" in script:
                    return 900.0
                return {"cx": 843.0, "cy": 473.0, "h": 900.0, "w": 1200.0}

        return DummyPage()


def test_bare_numbers_are_mm():
    # The old parser read anything <= 25 as centimetres.
    assert parse_mm(10) == 10.0
    assert parse_mm("10") == 10.0
    assert parse_mm(300) == 300.0


def test_units_are_honoured():
    assert parse_mm("10 cm") == 100.0
    assert parse_mm("2in") == 50.8
    assert parse_mm("1.5 m") == 1500.0
    assert parse_mm("50mm") == 50.0


def test_missing_value_uses_default():
    assert parse_mm(None) is None
    assert parse_mm(None, default_mm=20.0) == 20.0
    assert parse_mm("wide", default_mm=7.0) == 7.0


def test_mm_space_converts_and_flips_y():
    d = DummyDriver()
    x, y = asyncio.run(_ensure_viewport_coords(d, (50.0, 50.0)))
    assert x > 843.0  # +X is right
    assert y < 473.0  # +Y is up in CAD, down on screen


def test_large_mm_coordinate_is_not_mistaken_for_pixels():
    """A 300mm coordinate must still be scaled, not passed through."""
    d = DummyDriver()
    x, y = asyncio.run(_ensure_viewport_coords(d, (300.0, 0.0)))
    assert x != 300.0
    assert x > 843.0


def test_px_space_passes_through():
    d = DummyDriver()
    token = COORD_SPACE.set("px")
    try:
        assert asyncio.run(_ensure_viewport_coords(d, (300.0, 120.0))) == (300.0, 120.0)
    finally:
        COORD_SPACE.reset(token)


def test_origin_maps_to_canvas_centre():
    d = DummyDriver()
    assert asyncio.run(_ensure_viewport_coords(d, (0.0, 0.0))) == (843.0, 473.0)
