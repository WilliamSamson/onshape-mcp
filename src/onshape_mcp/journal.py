"""Append-only action journal. Every UI op is recorded for undo/replay/debug.

This file lives in `./state/` and is gitignored. Don't change that.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import settings


@dataclass
class JournalEntry:
    ts: float
    action_id: str
    tool: str
    args: dict[str, Any] = field(default_factory=dict)
    result: str = "ok"  # "ok" | "fail" | "skipped"
    note: str = ""
    screenshot: str | None = None  # relative path under state/ if captured

    @classmethod
    def new(cls, tool: str, args: dict[str, Any]) -> JournalEntry:
        return cls(
            ts=time.time(),
            action_id=uuid.uuid4().hex[:12],
            tool=tool,
            args=args,
        )


class Journal:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.journal_dir / "session.journal.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: JournalEntry) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-n:]
        return [json.loads(line) for line in lines if line.strip()]


journal = Journal()
