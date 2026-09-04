"""Closed-loop agent runner. Screenshot -> Gemini -> dispatch -> repeat.

Used by both the MCP `act()` tool and the run_task CLI. The dispatch
table + system prompt live in `dispatch.py` so the two callers can't
drift apart.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dispatch import build_agent_system_prompt, dispatch, parse_decision
from .driver import OnshapeDriver
from .vision import GeminiWeb

STUCK_THRESHOLD = 5  # unchanged screenshots in a row -> stop


@dataclass
class StepRecord:
    step: int
    decision: dict[str, Any]
    ok: bool
    error: str | None = None
    elapsed_s: float = 0.0


@dataclass
class LoopResult:
    goal: str
    steps: list[StepRecord] = field(default_factory=list)
    completed: bool = False
    final_screenshot: Path | None = None
    stop_reason: str = ""

    def summary(self) -> str:
        if self.completed:
            last = self.steps[-1].decision if self.steps else {}
            return f"completed in {len(self.steps)} steps: {last.get('summary', '')}"
        return f"stopped ({self.stop_reason}) after {len(self.steps)} steps"


class AgentLoop:
    def __init__(
        self,
        driver: OnshapeDriver | None = None,
        vision: GeminiWeb | None = None,
        stuck_threshold: int = STUCK_THRESHOLD,
    ) -> None:
        self.driver = driver
        self.vision = vision
        self.stuck_threshold = stuck_threshold

    async def _ensure(self) -> tuple[OnshapeDriver, GeminiWeb]:
        if self.driver is None:
            self.driver = OnshapeDriver()
            await self.driver.start(headless=True)
            await self.driver.open()
        if self.vision is None:
            self.vision = GeminiWeb()
        # Warm the vision client. The first call has higher latency
        # because of init + token exchange. Doing it before the loop
        # keeps the per-step timing predictable.
        await self.vision._ensure_client()
        return self.driver, self.vision

    async def close(self) -> None:
        if self.vision is not None:
            await self.vision.close()
            self.vision = None
        if self.driver is not None:
            await self.driver.close()
            self.driver = None

    async def run(self, goal: str, max_steps: int = 25) -> LoopResult:
        d, v = await self._ensure()
        result = LoopResult(goal=goal)
        last_hash: str | None = None
        unchanged = 0

        system_prompt = build_agent_system_prompt()
        history: list[dict[str, Any]] = []

        # Maintain a single chat session for this task run to prevent
        # spawning multiple separate chats per step.
        chat_session = await v.new_session()

        last_vertex: tuple[float, float] | None = None

        for step in range(max_steps):
            t0 = time.monotonic()
            shot = await d.screenshot(f"task_step_{step:02d}.png")
            h = hashlib.sha256(shot.read_bytes()).hexdigest()
            if h == last_hash:
                unchanged += 1
                if unchanged >= self.stuck_threshold:
                    result.stop_reason = f"stuck after {self.stuck_threshold} unchanged screenshots"
                    break
            else:
                unchanged = 0
            last_hash = h

            history_text = ""
            for r in history[-3:]:
                history_text += f"\nStep {r['step']}: {r['decision']}\n"
            vertex_text = f"\nLast drawn vertex on canvas: {last_vertex}\n" if last_vertex else ""
            prompt = (
                f"{system_prompt}\n\n"
                f"---\n"
                f"User goal: {goal}\n\n"
                f"Recent action history:{history_text}{vertex_text}\n"
                f"Step {step + 1}/{max_steps}. Look at the latest screenshot. "
                "Reply ONLY with a JSON object: "
                '{"tool": "<tool_name>", "args": {...}} OR {"done": true, "summary": "..."}'
            )
            try:
                answer = await v.ask_with_image(prompt, shot, session=chat_session)
            except Exception as e:
                result.steps.append(
                    StepRecord(
                        step,
                        {"error": f"vision: {e}"},
                        ok=False,
                        error=str(e),
                        elapsed_s=time.monotonic() - t0,
                    )
                )
                result.stop_reason = f"vision error: {e}"
                break

            decision = parse_decision(answer)
            history.append({"step": step, "decision": decision})
            if decision.get("done"):
                if str(decision.get("summary", "")).startswith("Could not parse decision"):
                    rec = StepRecord(
                        step,
                        decision,
                        ok=False,
                        error=decision.get("summary"),
                        elapsed_s=time.monotonic() - t0,
                    )
                    result.steps.append(rec)
                    continue
                result.completed = True
                result.steps.append(
                    StepRecord(step, decision, ok=True, elapsed_s=time.monotonic() - t0)
                )
                break

            tool = decision.get("tool")
            args = decision.get("args", {}) or {}
            rec = StepRecord(
                step, {"tool": tool, "args": args}, ok=True, elapsed_s=time.monotonic() - t0
            )
            try:
                action_res = await dispatch(d, tool, args)
                if (
                    hasattr(action_res, "meta")
                    and isinstance(action_res.meta, dict)
                    and "last_vertex" in action_res.meta
                ):
                    last_vertex = tuple(action_res.meta["last_vertex"])
            except Exception as e:
                rec.ok = False
                rec.error = f"{type(e).__name__}: {e}"
            rec.elapsed_s = time.monotonic() - t0
            result.steps.append(rec)
            if rec.ok:
                unchanged = 0
            status_str = (
                f"ERROR {rec.error}"
                if rec.error
                else f"{tool}({json.dumps(args, ensure_ascii=False)})"
            )
            print(f"  step {step}: {status_str} ({rec.elapsed_s:.1f}s)", flush=True)
            # brief beat so the UI has time to paint
            await asyncio.sleep(0.4)

        result.final_screenshot = await d.screenshot("task_final.png")
        if not result.completed and not result.stop_reason:
            result.stop_reason = f"max_steps ({max_steps}) reached"
        return result


def build_loop() -> AgentLoop:
    """Factory. Caller can override driver/vision if they already have one."""
    return AgentLoop()


def run_sync(goal: str, max_steps: int = 25) -> LoopResult:
    """Convenience wrapper for non-async callers."""
    return asyncio.run(AgentLoop().run(goal, max_steps=max_steps))
