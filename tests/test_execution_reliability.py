"""Offline regressions for execution status, progress detection and stdio."""
import ast
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from onshape_mcp import fast_exec, loop
from onshape_mcp.intent import Action, Plan
from onshape_mcp.ui_actions import Result


def run_loop(tmp_path, monkeypatch, action_result, frames=None, max_steps=5):
    shot = tmp_path / 'screen.png'
    frames = iter(frames or [b'unchanged'] * (max_steps + 1))

    async def screenshot(name):
        shot.write_bytes(next(frames))
        return shot

    driver = AsyncMock()
    driver.screenshot.side_effect = screenshot
    vision = AsyncMock()
    vision.ask_with_image.return_value = '{"tool":"view.fit","args":{}}'
    monkeypatch.setattr(loop, 'dispatch', AsyncMock(return_value=action_result))
    monkeypatch.setattr(loop.asyncio, 'sleep', AsyncMock())
    return asyncio.run(loop.AgentLoop(driver, vision, stuck_threshold=2).run('test', max_steps))


@pytest.mark.parametrize('result', [Result(False, 'not active'), {'ok': False, 'error': 'not active'}])
def test_loop_records_returned_failure(tmp_path, monkeypatch, result):
    outcome = run_loop(tmp_path, monkeypatch, result, max_steps=1)
    assert outcome.steps[0].ok is False
    assert 'not active' in outcome.steps[0].error


def test_successful_noops_still_stop(tmp_path, monkeypatch):
    outcome = run_loop(tmp_path, monkeypatch, Result(True))
    assert outcome.stop_reason == 'stuck after 2 unchanged screenshots'
    assert len(outcome.steps) == 2


def test_visual_progress_resets_counter(tmp_path, monkeypatch):
    outcome = run_loop(tmp_path, monkeypatch, Result(True), [b'a', b'a', b'b', b'b', b'c', b'c'])
    assert outcome.stop_reason == 'max_steps (5) reached'


def test_loop_diagnostics_use_stderr(tmp_path, monkeypatch, capsys):
    run_loop(tmp_path, monkeypatch, Result(True), max_steps=1)
    streams = capsys.readouterr()
    assert streams.out == ''
    assert 'step 0' in streams.err


@pytest.mark.parametrize('result', [Result(True), Result(False, 'failed')])
def test_fast_diagnostics_use_stderr(monkeypatch, capsys, result):
    driver = AsyncMock()
    driver.screenshot.side_effect = RuntimeError('screenshot failed')
    monkeypatch.setattr(fast_exec, 'dispatch', AsyncMock(return_value=result))
    asyncio.run(fast_exec.execute(driver, Plan([Action('view.fit')], 'test')))
    streams = capsys.readouterr()
    assert streams.out == ''
    assert '[0]' in streams.err
    assert '[warn]' in streams.err


@pytest.mark.parametrize('name', ['driver', 'vision', 'loop', 'fast_exec'])
def test_runtime_prints_explicitly_use_stderr(name):
    import importlib
    module = importlib.import_module(f'onshape_mcp.{name}')
    tree = ast.parse(Path(module.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print':
            assert any(k.arg == 'file' and ast.unparse(k.value) == 'sys.stderr' for k in node.keywords)
