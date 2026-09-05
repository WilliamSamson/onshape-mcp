"""Advanced sketch tools verification script.
Tests Spline, Fillet, Offset, and Mirror operations against live Onshape.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from onshape_mcp.driver import OnshapeDriver
from onshape_mcp import ui_actions


async def clean_features(page: object) -> None:
    import re
    for _ in range(15):
        try:
            loc = page.locator("span.os-list-item-name").filter(
                has_text=re.compile(r"^(Sketch|Extrude)")
            )
            if await loc.count() == 0:
                break
            await loc.first.click(timeout=1500)
            await asyncio.sleep(0.2)
            await page.keyboard.press("Delete")
            await asyncio.sleep(0.4)
        except Exception:
            break


async def test_spline(d: OnshapeDriver) -> bool:
    print("\n--- Test 1: Spline Shape ---")
    await clean_features(d.page)
    # Start sketch on Top plane
    await ui_actions.sketch_start(d, plane_name="Top")
    # Draw smooth S-curve spline through 5 points in CAD coordinates
    points = [
        (-80.0, -40.0),
        (-40.0, 40.0),
        (0.0, 0.0),
        (40.0, -40.0),
        (80.0, 40.0),
    ]
    r_spline = await ui_actions.sketch_spline(d, points)
    print(f"  Spline action: ok={r_spline.ok} ({r_spline.note})")
    await ui_actions.sketch_exit(d)
    shot = await d.screenshot("proof_spline.png")
    print(f"  Saved screenshot: {shot}")
    return r_spline.ok


async def test_fillet(d: OnshapeDriver) -> bool:
    print("\n--- Test 2: Rectangle with Fillet ---")
    await clean_features(d.page)
    # Start sketch on Top plane
    await ui_actions.sketch_start(d, plane_name="Top")
    # Draw 10cm x 10cm centered box
    r_rect = await ui_actions.sketch_rectangle(d, centered=True, width="10 cm", height="10 cm")
    print(f"  Rectangle action: ok={r_rect.ok}")
    # Fillet at top-left corner
    # In CAD coords, centered 10cm box extends from -5cm to +5cm (-163px to +163px)
    cx, cy = await ui_actions.get_canvas_origin(d)
    # Pick corner near top-left (-50mm, 50mm in CAD space -> cx-160, cy-160 in pixels)
    corner_xy = (cx - 160.0, cy - 160.0)
    r_fillet = await ui_actions.sketch_fillet(d, corner_xy, radius_mm=15.0)
    print(f"  Fillet action: ok={r_fillet.ok} ({r_fillet.note})")
    await ui_actions.sketch_exit(d)
    shot = await d.screenshot("proof_fillet.png")
    print(f"  Saved screenshot: {shot}")
    return r_rect.ok and r_fillet.ok


async def test_offset(d: OnshapeDriver) -> bool:
    print("\n--- Test 3: Offset Geometry ---")
    await clean_features(d.page)
    # Start sketch on Top plane
    await ui_actions.sketch_start(d, plane_name="Top")
    # Draw circle centered at origin with radius 40mm
    r_circ = await ui_actions.sketch_circle(d, centered=True, radius_px=50.0)
    print(f"  Circle action: ok={r_circ.ok}")
    # Offset circle
    cx, cy = await ui_actions.get_canvas_origin(d)
    perimeter_pt = (cx + 50.0, cy)
    side_pt = (cx + 80.0, cy)
    r_offset = await ui_actions.sketch_offset(d, perimeter_pt, distance_mm=10.0, side_xy=side_pt)
    print(f"  Offset action: ok={r_offset.ok} ({r_offset.note})")
    await ui_actions.sketch_exit(d)
    shot = await d.screenshot("proof_offset.png")
    print(f"  Saved screenshot: {shot}")
    return r_circ.ok and r_offset.ok


async def test_mirror(d: OnshapeDriver) -> bool:
    print("\n--- Test 4: Construction Line & Symmetrical Mirror ---")
    await clean_features(d.page)
    # Start sketch on Top plane
    await ui_actions.sketch_start(d, plane_name="Top")
    cx, cy = await ui_actions.get_canvas_origin(d)
    
    # 1. Draw vertical construction centerline from (0, -100) to (0, 100)
    await ui_actions.sketch_construction(d)  # toggle construction mode on
    await ui_actions.sketch_line(d, (0.0, -100.0), (0.0, 100.0))
    await ui_actions.sketch_construction(d)  # toggle construction mode off
    print("  Construction centerline drawn")

    # 2. Draw a circle on the left side: center at (-60, 0), radius 25mm
    circle_center = (-60.0, 0.0)
    r_circ = await ui_actions.sketch_circle(d, center=circle_center, radius_px=35.0)
    print(f"  Left circle drawn: ok={r_circ.ok}")

    # 3. Mirror across centerline
    centerline_pt = (cx, cy)
    entity_pt = (cx - 60.0 * 3.25, cy)
    r_mirror = await ui_actions.sketch_mirror(d, centerline_pt, entity_pt)
    print(f"  Mirror action: ok={r_mirror.ok} ({r_mirror.note})")

    await ui_actions.sketch_exit(d)
    shot = await d.screenshot("proof_mirror.png")
    print(f"  Saved screenshot: {shot}")
    return r_circ.ok and r_mirror.ok


async def main() -> None:
    t0 = time.monotonic()
    d = OnshapeDriver()
    try:
        await d.start(headless=True)
        await d.open()

        # Run tests
        res_spline = await test_spline(d)
        res_fillet = await test_fillet(d)
        res_offset = await test_offset(d)
        res_mirror = await test_mirror(d)

        print("\n================ TEST SUMMARY ================")
        print(f"1. Spline shape: {'PASS' if res_spline else 'FAIL'}")
        print(f"2. Fillet:       {'PASS' if res_fillet else 'FAIL'}")
        print(f"3. Offset:       {'PASS' if res_offset else 'FAIL'}")
        print(f"4. Mirror:       {'PASS' if res_mirror else 'FAIL'}")
        print(f"Total test time: {time.monotonic() - t0:.1f}s")
        print("==============================================")
    finally:
        await d.close()


if __name__ == "__main__":
    asyncio.run(main())
