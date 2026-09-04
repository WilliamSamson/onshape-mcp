"""Run a CAD task from the command line.

Usage:
    python3 scripts/run_task.py "create a 5x5 square and extrude it 5mm into a cube"

What it does:
  1. Initialise the driver + Gemini web vision.
  2. Run the same closed-loop agent as the MCP act() tool.
  3. Print each step to stdout as it happens.
  4. Save the final screenshot to state/task_final.png.

This is the script you run to test end-to-end without wiring up an
MCP client. It uses the same dispatch + system prompt as the MCP
act() tool, so behaviour is identical.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from onshape_mcp.loop import AgentLoop  # noqa: E402


async def main(goal: str, max_steps: int = 25) -> int:
    loop = AgentLoop()
    try:
        result = await loop.run(goal, max_steps=max_steps)
    finally:
        await loop.close()

    for rec in result.steps:
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
    print(f"=== {result.summary()} ===")
    print(f"final screenshot: {result.final_screenshot}")
    return 0 if result.completed else 1


def json_compact(d: dict) -> str:
    try:
        import json

        return json.dumps(d, ensure_ascii=False)
    except Exception:
        return str(d)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python3 scripts/run_task.py '<goal>' [max_steps]")
        raise SystemExit(2)
    goal = sys.argv[1]
    max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    raise SystemExit(asyncio.run(main(goal, max_steps)))
