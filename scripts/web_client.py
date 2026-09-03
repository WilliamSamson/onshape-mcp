"""Gemini-MCP web client. Browser UI that drives the Onshape agent loop.

Run with:
    python3 scripts/web_client.py

Then open http://localhost:8765 in any browser. Type a goal like
"create a 5x5mm cube" and watch it execute. Each step + the live
viewport screenshot stream back as it runs.

This is what "MCP-aware client but for Gemini" looks like: the LLM is
Gemini web (cookie auth, no API bill), the tools are the onshape-mcp
datasheet, the transport is a tiny Flask app instead of MCP stdio.
Same AgentLoop, same dispatch, same prompt.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from queue import Queue

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from flask import Flask, Response, jsonify, request, send_from_directory  # noqa: E402

from onshape_mcp.config import settings  # noqa: E402
from onshape_mcp.loop import AgentLoop, StepRecord  # noqa: E402

app = Flask(
    __name__,
    static_folder=str(REPO_ROOT / "state"),
    template_folder=str(REPO_ROOT / "scripts" / "templates"),
)

# Single shared loop. /act submits goals; the loop runs them serially.
_loop = AgentLoop()
_loop_lock = threading.Lock()
_event_queue: Queue = Queue()


def _run_goal_sync(goal: str, max_steps: int) -> dict:
    """Run the async loop from a Flask thread."""
    async def go():
        return await _loop.run(goal, max_steps=max_steps)

    return asyncio.run(go())


@app.route("/")
def index():
    return send_from_directory(str(REPO_ROOT / "scripts" / "templates"), "index.html")


@app.route("/state/<path:filename>")
def state_file(filename: str):
    """Serve the latest screenshots so the UI can poll them."""
    return send_from_directory(str(settings.journal_dir), filename)


@app.route("/act", methods=["POST"])
def act():
    data = request.get_json(silent=True) or {}
    goal = (data.get("goal") or "").strip()
    max_steps = int(data.get("max_steps") or 25)
    if not goal:
        return jsonify({"error": "missing goal"}), 400
    if _loop_lock.locked():
        return jsonify({"error": "busy with previous task"}), 409
    with _loop_lock:
        try:
            result = _run_goal_sync(goal, max_steps)
        except Exception as e:
            return jsonify({"error": f"{type(e).__name__}: {e}"}), 500
    return jsonify(
        {
            "goal": result.goal,
            "completed": result.completed,
            "summary": result.summary(),
            "stop_reason": result.stop_reason,
            "steps": [
                {
                    "step": r.step,
                    "tool": r.decision.get("tool"),
                    "args": r.decision.get("args", {}),
                    "ok": r.ok,
                    "error": r.error,
                    "elapsed_s": round(r.elapsed_s, 1),
                }
                for r in result.steps
            ],
            "final_screenshot": str(result.final_screenshot) if result.final_screenshot else None,
        }
    )


@app.route("/ping")
def ping():
    return jsonify({"ok": True, "settings": repr(settings)})


def main() -> None:
    host = "127.0.0.1"
    port = 8765
    print(f"[web_client] open http://{host}:{port} in your browser")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
