"""Run a CAD task from the command line.

Usage:
    python3 scripts/run_task.py "create a 5x5 square and extrude it 5mm into a cube"

The script tries two execution paths:

1. **Fast path** (intent parser + direct executor) — no LLM calls, ~10s.
   Handles deterministic tasks like "draw a 10x5 box on the top plane".

2. **Vision loop** (Gemini LLM feedback loop) — fallback for novel prompts.
   Takes screenshots, asks the LLM what to do next, repeats.

Use --slow to force the vision loop even if the fast path matches.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from onshape_mcp.driver import OnshapeDriver  # noqa: E402
from onshape_mcp.intent import parse as parse_intent  # noqa: E402
from onshape_mcp.fast_exec import execute as fast_execute  # noqa: E402
from onshape_mcp.loop import AgentLoop  # noqa: E402


async def _clean_features(page: object) -> None:
    """Delete all Sketch/Extrude features from the feature tree."""
    import re

    for _ in range(15):
        loc = page.locator("span.os-list-item-name").filter(  # type: ignore[attr-defined]
            has_text=re.compile(r"^(Sketch|Extrude)")
        )
        if await loc.count() == 0:
            break
        await loc.first.click()
        await asyncio.sleep(0.2)
        await page.keyboard.press("Delete")  # type: ignore[attr-defined]
        await asyncio.sleep(0.4)


async def main(
    goal: str,
    max_steps: int = 25,
    clean: bool = False,
    force_slow: bool = False,
) -> int:
    t_start = time.monotonic()

    # Try fast path first
    plan = None if force_slow else parse_intent(goal)

    if plan is not None:
        print(f"[fast] parsed plan: {len(plan.actions)} actions")
        for i, a in enumerate(plan.actions):
            print(f"  [{i}] {a.tool}({a.args})")
        print()

        d = OnshapeDriver()
        try:
            await d.start(headless=True)
            await d.open()
            if clean:
                await _clean_features(d.page)
            result = await fast_execute(d, plan)
        finally:
            await d.close()

        total_wall_s = time.monotonic() - t_start
        print()
        status = "✓" if result.ok else "✗"
        print(f"=== {status} {result.summary()} ===")
        print(f"Total wall time: {total_wall_s:.1f}s")
        print(f"final screenshot: {result.final_screenshot}")
        return 0 if result.ok else 1

    # Fallback: vision loop
    print("[slow] no fast-path match, using vision loop")
    loop = AgentLoop()
    try:
        if clean:
            d_loop, _ = await loop._ensure()
            await _clean_features(d_loop.page)
        result_loop = await loop.run(goal, max_steps=max_steps)
    finally:
        await loop.close()

    total_wall_s = time.monotonic() - t_start
    for rec in result_loop.steps:
        if rec.error:
            print(f"  step {rec.step}: ERROR {rec.error} ({rec.elapsed_s:.1f}s)")
        elif rec.decision.get("done"):
            print(
                f"  step {rec.step}: DONE — {rec.decision.get('summary', '')} ({rec.elapsed_s:.1f}s)"
            )
        else:
            tool = rec.decision.get("tool")
            args = rec.decision.get("args", {})
            print(f"  step {rec.step}: {tool}({json_compact(args)}) ({rec.elapsed_s:.1f}s)")

    print()
    print(f"=== {result_loop.summary()} ===")
    print(f"Total wall time: {total_wall_s:.1f}s (Agent loop: {result_loop.total_elapsed_s:.1f}s)")
    print(f"final screenshot: {result_loop.final_screenshot}")
    return 0 if result_loop.completed else 1


def json_compact(d: dict) -> str:
    try:
        import json

        return json.dumps(d, ensure_ascii=False)
    except Exception:
        return str(d)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 scripts/run_task.py '<goal>' [max_steps] [--clean] [--slow]")
        raise SystemExit(2)
    clean = "--clean" in sys.argv
    force_slow = "--slow" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    goal = args[0]
    max_steps = int(args[1]) if len(args) > 1 else 25
    raise SystemExit(asyncio.run(main(goal, max_steps, clean=clean, force_slow=force_slow)))
