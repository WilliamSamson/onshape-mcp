import asyncio

from onshape_mcp.dispatch import TOOL_DISPATCH
from onshape_mcp.ui_actions import _ensure_viewport_coords


class DummyDriver:
    async def viewport_box(self):
        return {"w": 1440.0, "h": 900.0}

    @property
    def page(self):
        class DummyPage:
            async def evaluate(self, script):
                return {"cx": 843.0, "cy": 473.0}

        return DummyPage()


def test_origin_mapping():
    d = DummyDriver()
    pt = asyncio.run(_ensure_viewport_coords(d, (0.0, 0.0)))
    assert pt == (843.0, 473.0)


def test_cad_relative_coords():
    d = DummyDriver()
    # Quadrant 1 (+X, +Y in CAD -> +X, -Y screen)
    q1 = asyncio.run(_ensure_viewport_coords(d, (50.0, 50.0)))
    assert q1[0] > 843.0
    assert q1[1] < 473.0

    # Quadrant 2 (-X, +Y in CAD -> -X, -Y screen)
    q2 = asyncio.run(_ensure_viewport_coords(d, (-50.0, 50.0)))
    assert q2[0] < 843.0
    assert q2[1] < 473.0

    # Quadrant 3 (-X, -Y in CAD -> -X, +Y screen)
    q3 = asyncio.run(_ensure_viewport_coords(d, (-50.0, -50.0)))
    assert q3[0] < 843.0
    assert q3[1] > 473.0

    # Quadrant 4 (+X, -Y in CAD -> +X, +Y screen)
    q4 = asyncio.run(_ensure_viewport_coords(d, (50.0, -50.0)))
    assert q4[0] > 843.0
    assert q4[1] > 473.0


def test_dispatch_has_quadrant_tools():
    assert "sketch.rectangle" in TOOL_DISPATCH
    assert "sketch.circle" in TOOL_DISPATCH
    assert "sketch.start" in TOOL_DISPATCH
