import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from onshape_mcp import interactive, sketch_state
from onshape_mcp.interactive import InteractiveSession
from onshape_mcp.ui_actions import Result


class Driver:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.model = {'features': [], 'featureStates': {}}
        self.view = 'initial'
        self.n = 0
        self.page = SimpleNamespace(url='https://cad.onshape.com/documents/d/w/w/e/e',
                                    evaluate=AsyncMock(), locator=lambda s: SimpleNamespace(count=AsyncMock(return_value=0)))
        self.viewport_box = AsyncMock(return_value={'w': 1000, 'h': 800})
        self.click = AsyncMock()
        self.press_key = AsyncMock()
        self.drag = AsyncMock()

    async def screenshot(self, name):
        self.n += 1
        path = self.root / f'{self.n}.png'
        path.write_bytes((self.view + json.dumps(self.model, sort_keys=True)).encode())
        return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    driver = Driver(tmp_path)
    async def read(d):
        return copy.deepcopy(d.model)
    monkeypatch.setattr(sketch_state, 'read_features', read)
    session = InteractiveSession(driver, tmp_path / 'requests')
    dispatch = AsyncMock(return_value=Result(True))
    monkeypatch.setattr(interactive, 'dispatch', dispatch)
    return session, driver, dispatch


def run(coro):
    return asyncio.run(coro)


def steps(n=2):
    return [{'tool': 'view.fit', 'args': {}, 'space': 'px'} for _ in range(n)]


def test_begin_does_not_draw_and_next_executes_one(env):
    s, _, dispatch = env
    run(s.begin('r', 'draw', steps()))
    dispatch.assert_not_awaited()
    result = run(s.next())
    assert result['phase'] == 'ready'
    assert result['index'] == 0
    assert dispatch.await_count == 1
    assert Path(result['screenshot']).exists()


def test_duplicate_request_never_replays_including_restart(env):
    s, d, dispatch = env
    run(s.begin('r', 'draw', steps(1)))
    run(s.next())
    restarted = InteractiveSession(d, s.directory)
    assert run(restarted.begin('r', 'draw', steps(1)))['duplicate']
    assert dispatch.await_count == 1
    with pytest.raises(ValueError):
        run(restarted.begin('r', 'different', steps(1)))


def test_uncertain_request_is_not_replayed(env):
    s, d, dispatch = env
    run(s.begin('r', 'draw', steps()))
    s.current['status'] = 'running'
    s.save()
    restarted = InteractiveSession(d, s.directory)
    assert run(restarted.begin('r', 'draw', steps()))['request']['status'] == 'running'
    dispatch.assert_not_awaited()


def test_pause_resume_and_failure_consumes_attempt(env):
    s, _, dispatch = env
    run(s.begin('r', 'draw', steps()))
    s.pause()
    with pytest.raises(ValueError): run(s.next())
    run(s.resume())
    dispatch.return_value = Result(False, 'missed edge')
    assert run(s.next())['phase'] == 'paused'
    assert s.current['index'] == 1
    run(s.resume())
    dispatch.return_value = Result(True)
    assert run(s.next())['phase'] == 'complete'
    assert dispatch.await_count == 2


def test_pause_during_action_stops_at_boundary(env):
    s, _, dispatch = env
    async def action(*a, **kw):
        s.pause()
        return Result(True)
    dispatch.side_effect = action
    run(s.begin('r', 'draw', steps()))
    assert run(s.next())['phase'] == 'paused'
    assert dispatch.await_count == 1


def test_changed_view_stops_before_dispatch(env):
    s, d, dispatch = env
    run(s.begin('r', 'draw', steps()))
    d.view = 'zoomed'
    with pytest.raises(ValueError, match='Drawing/view changed'): run(s.next())
    dispatch.assert_not_awaited()
    assert s.phase == 'paused'


def test_handoff_and_resume_preserve_manual_changes(env):
    s, d, dispatch = env
    run(s.begin('r', 'draw', steps()))
    run(s.handoff())
    d.model['features'] = [{'featureId': 'manual'}]
    run(s.resume())
    assert s.current['after']['features'][0]['feature_id'] == 'manual'
    run(s.next())
    run(s.cancel())
    with pytest.raises(ValueError, match='Manual edits'): run(s.undo())


def test_selection_preview_and_expiry(env):
    s, d, _ = env
    frame = run(s.frame())
    selected = run(s.select('left edge', 200, 200, frame['frame_id']))
    assert selected['confirmation_required']
    d.click.assert_not_awaited()
    with pytest.raises(ValueError, match='Confirm'): run(s.edit(selected['handle'], 'delete'))
    d.view = 'changed'
    with pytest.raises(ValueError, match='Drawing/view changed'):
        run(s.edit(selected['handle'], 'delete', True))
    d.click.assert_not_awaited()


def test_selection_revise_keeps_handle(env):
    s, d, _ = env
    run(s.begin('r', 'move point', steps()))
    frame = run(s.frame())
    target = run(s.select('point', 100, 100, frame['frame_id']))
    new_steps = [{'tool': 'selection.edit', 'args': {'handle': target['handle'], 'operation': 'move',
                 'confirmed': True, 'x': 110, 'y': 120}}]
    run(s.revise(new_steps))
    result = run(s.next())
    assert result['ok']
    d.drag.assert_awaited_once_with((100, 100), (110.0, 120.0))
    assert not result['result']['verified']
    assert not s.selections


@pytest.mark.parametrize('tool', ['sketch.create', 'sketch.m4_profile', 'document.undo', 'doc.open', 'no.such.tool'])
def test_reject_hidden_batch_api_and_history_steps(env, tool):
    s, _, dispatch = env
    with pytest.raises(ValueError): run(s.begin('r', 'bad', [{'tool': tool}]))
    dispatch.assert_not_awaited()


@pytest.mark.parametrize('point', [(-1, 2), (1001, 2), (float('nan'), 2)])
def test_selection_out_of_bounds(env, point):
    s, _, _ = env
    frame = run(s.frame())
    with pytest.raises(ValueError): run(s.select('bad', *point, frame['frame_id']))


def test_one_native_undo_checks_checkpoint(env, monkeypatch):
    s, d, dispatch = env
    run(s.begin('r', 'one sketch', [{'tool':'sketch.start'}, {'tool':'sketch.exit'}]))
    run(s.next())
    async def commit(*a, **kw):
        d.model['features'] = [{'featureId': 'created', 'name': 'Sketch 1'}]
        return Result(True)
    dispatch.side_effect = commit
    run(s.next())
    async def undo(driver):
        driver.model['features'] = []
        return Result(True)
    mock = AsyncMock(side_effect=undo)
    monkeypatch.setattr(interactive.ui_actions, 'doc_undo', mock)
    assert run(s.undo())['restored']
    mock.assert_awaited_once()
    assert s.phase == 'undone'


def test_external_edit_prevents_group_undo(env, monkeypatch):
    s, d, _ = env
    run(s.begin('r', 'one sketch', [{'tool':'sketch.start'}, {'tool':'sketch.exit'}]))
    run(s.next()); run(s.next())
    d.model['features'] = [{'featureId': 'manual'}]
    mock = AsyncMock()
    monkeypatch.setattr(interactive.ui_actions, 'doc_undo', mock)
    with pytest.raises(ValueError): run(s.undo())
    mock.assert_not_awaited()


def payload(expression='2.5 cm', state='OK'):
    return {'features':[{'featureId':'f','constraints':[{'constraintId':'c', 'parameters':[
        {'parameterId':'length', 'expression':expression}]}]}], 'featureStates':{'f':{'featureStatus':state}}}


def test_dimension_readback_and_solver_status():
    assert sketch_state.verify_dimension(payload(), 'f', 'c', 25)['verified']
    for data in (payload('26 mm'), payload('#width'), payload(state='ERROR'), payload(state=None)):
        assert not sketch_state.verify_dimension(data, 'f', 'c', 25)['verified']
    assert not sketch_state.verify_dimension(payload(), 'f', 'missing', 25)['verified']


def test_microversion_is_not_model_content():
    a, b = payload(), payload()
    a['sourceMicroversion'] = 'a'
    b['sourceMicroversion'] = 'b'
    assert sketch_state.fingerprint(a) == sketch_state.fingerprint(b)


@pytest.mark.parametrize('value', ['nan mm', 'inf mm', '25', 'x * mm', '1 mm + 1 mm'])
def test_unknown_dimension_expression_not_guessed(value):
    assert sketch_state.millimetres(value) is None


def test_unique_screenshot_names_cannot_escape_directory():
    from onshape_mcp.driver import OnshapeDriver
    from onshape_mcp.config import settings
    a, b = [OnshapeDriver._screenshot_path('../../same.png') for _ in range(2)]
    assert a != b
    assert a.parent == b.parent == settings.journal_dir


def test_server_loop_borrows_same_driver(monkeypatch):
    from onshape_mcp import server
    d, v = object(), object()
    monkeypatch.setattr(server, '_loop', None)
    monkeypatch.setattr(server, '_driver_lazy', AsyncMock(return_value=d))
    monkeypatch.setattr(server, '_vision_lazy', AsyncMock(return_value=v))
    loop = run(server._loop_lazy())
    assert loop.driver is d and loop.vision is v


def test_server_legacy_tools_block_during_interactive_request(monkeypatch):
    from onshape_mcp import server
    monkeypatch.setattr(server, '_interactive', SimpleNamespace(phase='paused'))
    lazy = AsyncMock()
    monkeypatch.setattr(server, '_driver_lazy', lazy)
    assert json.loads(run(server.onshape_view_fit()))['ok'] is False
    lazy.assert_not_awaited()


def test_restore_skips_uncertain_attempt(env):
    s, d, dispatch = env
    run(s.begin('r', 'draw', steps(2)))
    s.current['status'] = 'running'
    s.save()
    new = InteractiveSession(d, s.directory)
    restored = run(new.restore('r'))
    assert restored['request']['index'] == 1
    assert new.phase == 'paused'
    dispatch.assert_not_awaited()
    run(new.resume())
    run(new.next())
    assert dispatch.await_count == 1


def test_circle_propagates_dimension_failure(tmp_path, monkeypatch):
    from onshape_mcp import ui_actions as ui
    d = Driver(tmp_path)
    monkeypatch.setattr(ui, '_activate_sketch_tool', AsyncMock(return_value=Result(True)))
    monkeypatch.setattr(ui, 'get_canvas_origin', AsyncMock(return_value=(100, 100)))
    monkeypatch.setattr(ui, '_span_px', AsyncMock(return_value=(60, False)))
    monkeypatch.setattr(ui, 'sketch_dimension', AsyncMock(return_value=Result(False, 'missed')))
    monkeypatch.setattr(ui, '_record', lambda *a: None)
    monkeypatch.setattr(ui.asyncio, 'sleep', AsyncMock())
    result = run(ui.sketch_circle(d, radius_mm=20))
    assert not result.ok
    assert result.meta['dimension_applied'] is False


def test_inline_frame_is_real_image_content(tmp_path):
    from PIL import Image
    from onshape_mcp.server import _visual_result
    p = tmp_path / 'frame.png'
    Image.new('RGB', (30, 30), 'white').save(p)
    content = _visual_result({'ok': True, 'screenshot': str(p)})
    assert content[0].type == 'text'
    assert content[1].type == 'image'
    assert content[1].mimeType == 'image/png'


def test_mcp_tools_register_valid_schemas():
    from onshape_mcp.server import mcp
    tools = {tool.name: tool for tool in run(mcp.list_tools())}
    assert {'onshape_workflow', 'onshape_frame', 'onshape_select_target', 'onshape_verify_dimension'} <= tools.keys()
    assert 'restore' in tools['onshape_workflow'].inputSchema['properties']['command']['enum']


@pytest.mark.parametrize('urls,chosen,expected', [
    (['https://example.com', 'https://cad.onshape.com/documents/d/w/w/e/e'], '', 1),
    (['https://cad.onshape.com/documents/a/w/w/e/e', 'https://cad.onshape.com/documents/b/w/w/e/e'], '', None),
    (['https://cad.onshape.com/documents/a/w/w/e/e', 'https://cad.onshape.com/documents/b/w/w/e/e'], 'https://cad.onshape.com/documents/b/w/w/e/e', 1),
])
def test_cdp_selects_document_not_first_tab(monkeypatch, urls, chosen, expected):
    from onshape_mcp import driver as module
    pages = [SimpleNamespace(url=u, bring_to_front=AsyncMock()) for u in urls]
    context = SimpleNamespace(pages=pages, close=AsyncMock())
    for page in pages: page.context = context
    browser = SimpleNamespace(contexts=[context])
    pw = SimpleNamespace(chromium=SimpleNamespace(connect_over_cdp=AsyncMock(return_value=browser)), stop=AsyncMock())
    monkeypatch.setattr(module, 'async_playwright', lambda: SimpleNamespace(start=AsyncMock(return_value=pw)))
    monkeypatch.setattr(module.settings, 'cdp_url', 'http://localhost:9222')
    monkeypatch.setattr(module.settings, 'tab_url', chosen)
    d = module.OnshapeDriver()
    if expected is None:
        with pytest.raises(RuntimeError, match='Select exactly one'): run(d.start())
        for page in pages: page.bring_to_front.assert_not_awaited()
    else:
        assert run(d.start()) is pages[expected]
        run(d.close())
        context.close.assert_not_awaited()


def test_interactive_shapes_do_not_batch_hidden_dimensions(env):
    s, _, dispatch = env
    run(s.begin('r', 'rectangle', [{'tool': 'sketch.rectangle', 'args': {'width': 30, 'height': 20}}]))
    run(s.next())
    assert dispatch.await_args.args[2]['auto_dimension'] is False
