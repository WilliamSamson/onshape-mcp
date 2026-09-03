"""Smoke tests — no browser, no network, no LLM. Just shape."""

from onshape_mcp import tools as datasheet
from onshape_mcp.config import Settings
from onshape_mcp.journal import Journal, JournalEntry


def test_datasheet_has_tools() -> None:
    assert len(datasheet.ALL_TOOLS) >= 20
    for t in datasheet.ALL_TOOLS:
        assert t.name
        assert t.purpose
        assert t.status in {"planned", "stub", "working"}


def test_datasheet_lookup() -> None:
    s = datasheet.lookup("feature.extrude")
    assert s.purpose
    assert "sketch.active=false" in s.requires


def test_journal_round_trip(tmp_path) -> None:
    j = Journal(path=tmp_path / "t.journal.jsonl")
    j.append(JournalEntry.new("screenshot", {"name": "a.png"}))
    j.append(JournalEntry.new("ui.undo", {}))
    tail = j.tail()
    assert len(tail) == 2
    assert tail[0]["tool"] == "screenshot"
    assert tail[1]["tool"] == "ui.undo"


def test_settings_redacts_paths() -> None:
    s = Settings()
    rep = repr(s)
    # On purpose: repr must not echo cookie/profile paths.
    assert "playwright-profile" not in rep
    assert "gemini.cookies.json" not in rep
