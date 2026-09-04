"""Fast direct executor. Runs a parsed Plan against the Onshape driver
without any LLM calls. This is the fast path for deterministic tasks.

Typical execution: ~5-8s for sketch + dimension + commit, compared to
~60s with the vision loop.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dispatch import dispatch
from .driver import OnshapeDriver
from .intent import Plan


@dataclass
class FastResult:
    plan: Plan
    ok: bool
    total_elapsed_s: float = 0.0
    final_screenshot: Path | None = None
    step_times: list[tuple[str, float]] = None  # type: ignore[assignment]
    error: str | None = None

    def __post_init__(self) -> None:
        if self.step_times is None:
            self.step_times = []

    def summary(self) -> str:
        n = len(self.step_times)
        if self.ok:
            return f"completed {n} actions ({self.total_elapsed_s:.1f}s): {self.plan.summary}"
        return f"failed at action {n} ({self.total_elapsed_s:.1f}s): {self.error}"


async def execute(d: OnshapeDriver, plan: Plan) -> FastResult:
    """Execute a Plan's actions sequentially against the driver.
    No LLM calls, no screenshots between steps (except final).
    """
    t0 = time.monotonic()
    result = FastResult(plan=plan, ok=True)

    for i, action in enumerate(plan.actions):
        step_t0 = time.monotonic()
        tool = action.tool
        args = action.args
        try:
            await dispatch(d, tool, args)
            elapsed = time.monotonic() - step_t0
            result.step_times.append((f"{tool}({_compact(args)})", elapsed))
            print(f"  [{i}] {tool}({_compact(args)}) ({elapsed:.1f}s)", flush=True)
        except Exception as e:
            elapsed = time.monotonic() - step_t0
            result.step_times.append((f"{tool} ERROR", elapsed))
            result.ok = False
            result.error = f"{tool}: {e}"
            print(f"  [{i}] {tool} ERROR: {e} ({elapsed:.1f}s)", flush=True)
            break

    try:
        result.final_screenshot = await d.screenshot("task_final.png")
    except Exception as e:
        print(f"  [warn] could not capture final screenshot: {e}", flush=True)
    result.total_elapsed_s = time.monotonic() - t0
    return result


def _compact(d: dict[str, Any]) -> str:
    import json
    try:
        return json.dumps(d, ensure_ascii=False)
    except Exception:
        return str(d)
