"""Step-wise, UI-only editing with conservative state and retry guards.

The MCP client translates conversation into steps. This controller never runs
an invisible multi-step plan: each next() performs exactly one semantic action.
Read-only feature snapshots supply persisted-state evidence, not API edits.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import uuid
from pathlib import Path
from typing import Any

from . import sketch_state, ui_actions
from .dispatch import TOOL_DISPATCH, dispatch


class InteractiveSession:
    def __init__(self, driver: Any, directory: Path) -> None:
        self.driver = driver
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.lock = asyncio.Lock()
        self.phase = 'idle'
        self.current: dict[str, Any] | None = None
        self.selections: dict[str, dict[str, Any]] = {}
        self.last_frame: dict[str, Any] | None = None
        self.pause_requested = False
        self.events: list[dict[str, Any]] = []

    def event(self, kind: str, **data: Any) -> None:
        record = {'event': kind, 'request_id': (self.current or {}).get('request_id'), **data}
        self.events.append(record)
        with (self.directory / 'events.jsonl').open('a') as stream:
            stream.write(json.dumps(record) + '\n')

    def _path(self, request_id: str) -> Path:
        return self.directory / (hashlib.sha256(request_id.encode()).hexdigest() + '.json')

    def save(self) -> None:
        if self.current is not None:
            target = self._path(self.current['request_id'])
            temporary = target.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.current, indent=2))
            temporary.replace(target)

    async def frame(self) -> dict[str, Any]:
        # Markers are presentation only and excluded from freshness fingerprints.
        await self.driver.page.evaluate("document.getElementById('onshape-mcp-target')?.remove()")
        shot = await self.driver.screenshot('interactive')
        data = {'frame_id': uuid.uuid4().hex, 'screenshot': str(shot),
                'url': self.driver.page.url, 'digest': hashlib.sha256(shot.read_bytes()).hexdigest()}
        self.last_frame = data
        return data

    async def observe(self) -> dict[str, Any]:
        frame = await self.frame()
        try:
            payload = await sketch_state.read_features(self.driver)
            features = sketch_state.inventory(payload)
            digest = sketch_state.fingerprint(payload)
            error = None
        except Exception as exc:
            features, digest, error = [], None, str(exc)
        active = await self.driver.page.locator('.feature-dialog:not(.ns-dialog-default-hidden)').count() > 0
        return {**frame, 'sketch_active': active, 'features': features, 'model_digest': digest, 'inspection_error': error,
                'phase': self.phase, 'request_id': (self.current or {}).get('request_id'),
                'note': 'Feature inventory describes persisted state; uncommitted edits require visual inspection.'}

    @staticmethod
    def validate_steps(steps: list[dict[str, Any]]) -> None:
        if not steps or len(steps) > 100:
            raise ValueError('Supply 1–100 explicit steps')
        for step in steps:
            tool = step.get('tool')
            if tool not in TOOL_DISPATCH and tool != 'selection.edit':
                raise ValueError(f'Unknown step: {tool}')
            # No document switching, API construction, hidden batching or native
            # history operations inside a guarded interactive request.
            if tool in {'doc.open', 'doc.new', 'sketch.create', 'm4.profile', 'ui.undo', 'ui.redo',
                        'doc.undo', 'doc.redo', 'document.undo', 'document.redo', 'features.delete_all'} or 'm4' in str(tool):
                raise ValueError(f'{tool} is not a single interactive sketch step')
            if not isinstance(step.get('args', {}), dict) or step.get('space', 'px') not in ('px', 'mm'):
                raise ValueError('Each step needs object args and explicit px or mm space')

    async def begin(self, request_id: str, goal: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
        if not request_id.strip():
            raise ValueError('A stable request_id is required for retry protection')
        self.validate_steps(steps)
        signature = json.dumps({'goal': goal, 'steps': steps}, sort_keys=True)
        path = self._path(request_id)
        if path.exists():
            previous = json.loads(path.read_text())
            if previous['signature'] != signature:
                raise ValueError('request_id already belongs to a different request')
            # Never replay a completed or interrupted request after a retry/restart.
            return {'ok': True, 'duplicate': True, 'request': previous}
        if self.current and self.phase not in ('complete', 'cancelled', 'idle', 'undone'):
            raise ValueError('Finish or cancel the active request first')
        before = await self.observe()
        if before.get('sketch_active') and steps[0]['tool'] == 'sketch.start':
            raise ValueError('A sketch is already open; edit or close it instead of creating another')
        self.current = {'request_id': request_id, 'goal': goal, 'signature': signature, 'steps': steps,
                        'index': 0, 'status': 'ready', 'before': before, 'after': before,
                        'results': [], 'manual_handoff': False}
        self.phase, self.pause_requested = 'ready', False
        self.selections.clear()
        self.save()
        self.event('begin', goal=goal, frame=before['screenshot'])
        return {'ok': True, 'request': self.current, 'next': 'next executes one step only'}

    async def restore(self, request_id: str) -> dict[str, Any]:
        if self.current and self.phase not in ('idle', 'complete', 'cancelled', 'undone'):
            raise ValueError('An active request already owns the session')
        saved = json.loads(self._path(request_id).read_text())
        if saved['status'] in ('complete', 'cancelled', 'undone'):
            return {'ok': True, 'request': saved, 'note': 'Terminal request; no actions replayed'}
        if saved['status'] == 'running':
            saved['index'] += 1
            saved['results'].append({'ok': False, 'error': 'Interrupted action outcome unknown; inspect before revising. Attempt not replayed.'})
        self.current = saved
        self.phase, self.pause_requested = 'paused', True
        saved['status'], saved['manual_handoff'] = 'paused', True
        saved['after'] = await self.observe()
        self.save()
        self.event('restore')
        return {'ok': True, 'request': saved, 'note': 'Inspect current state, then resume or revise. No action replayed.'}

    async def _fresh(self, expected: dict[str, Any]) -> dict[str, Any]:
        current = await self.observe()
        if current['url'] != expected['url'] or current['digest'] != expected['digest'] or (
            expected.get('model_digest') and current['model_digest'] != expected['model_digest']
        ):
            self.phase = 'paused'
            self.selections.clear()
            raise ValueError('Drawing/view changed. Inspect and resume/reselect before editing.')
        return current

    def pause(self) -> dict[str, Any]:
        # No lock: an in-flight action finishes, but no subsequent action starts.
        self.pause_requested = True
        self.phase = 'paused'
        return {'ok': True, 'phase': 'paused', 'note': 'Pause takes effect at the action boundary.'}

    async def resume(self, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if self.current is None or self.phase not in ('paused', 'manual'):
            raise ValueError('There is no paused request')
        if steps is not None:
            self.validate_steps(steps)
            self.current['steps'] = self.current['steps'][:self.current['index']] + steps
        self.selections.clear()
        refreshed = await self.observe()
        if refreshed['model_digest'] != self.current['after']['model_digest'] or refreshed['digest'] != self.current['after']['digest']:
            self.current['manual_handoff'] = True
        self.current['after'] = refreshed
        self.pause_requested = False
        self.phase = 'ready'
        self.current['status'] = self.phase
        self.save()
        self.event('resume', frame=self.current['after']['screenshot'])
        return {'ok': True, 'phase': self.phase, 'observation': self.current['after']}

    async def revise(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        if self.current is None or self.phase not in ('ready', 'paused'):
            raise ValueError('Revise an active request; resume manual handoff first')
        self.validate_steps(steps)
        await self._fresh(self.current['after'])
        self.current['steps'] = self.current['steps'][:self.current['index']] + steps
        self.phase, self.pause_requested = 'ready', False
        self.current['status'] = 'ready'
        self.save()
        self.event('revise', remaining=len(steps))
        return {'ok': True, 'phase': 'ready', 'remaining': len(steps)}

    async def handoff(self) -> dict[str, Any]:
        if self.current is None:
            raise ValueError('Start a request before handing off')
        self.pause_requested, self.phase = True, 'manual'
        self.current['manual_handoff'] = True
        self.current['status'] = 'manual'
        self.selections.clear()
        self.save()
        self.event('manual_handoff')
        return {'ok': True, 'phase': 'manual', 'note': 'Edit in the browser, then resume with revised steps. Group undo disabled for this request.'}

    async def select(self, label: str, x: float, y: float, frame_id: str,
                     feature_id: str | None = None, entity_id: str | None = None) -> dict[str, Any]:
        if not self.last_frame or frame_id != self.last_frame['frame_id']:
            raise ValueError('Select from the latest frame_id')
        expected = self.last_frame.copy()
        await self._fresh(expected)
        size = await self.driver.viewport_box()
        if not all(math.isfinite(v) for v in (x, y)) or not (0 <= x < size['w'] and 0 <= y < size['h']):
            raise ValueError('Selection lies outside the viewport')
        if entity_id:
            payload = await sketch_state.read_features(self.driver)
            feature = next((f for f in sketch_state.inventory(payload) if f['feature_id'] == feature_id), None)
            ids = {e.get('entityId') for e in feature['entities']} if feature else set()
            ids |= {c.get('constraintId') for c in feature['constraints']} if feature else set()
            if entity_id not in ids:
                raise ValueError('Entity/constraint is absent from the named feature')
        handle = uuid.uuid4().hex
        self.selections[handle] = {'handle': handle, 'label': label, 'x': x, 'y': y,
                                   'feature_id': feature_id, 'entity_id': entity_id, 'frame': expected}
        await self.driver.page.evaluate('''({x,y,label}) => {
          const e=document.createElement('div'); e.id='onshape-mcp-target';
          e.textContent=label; Object.assign(e.style,{position:'fixed',left:x+'px',top:y+'px',
          border:'3px solid #ff9800',borderRadius:'8px',padding:'8px',color:'#fff',background:'#222',
          zIndex:'2147483647',pointerEvents:'none'}); document.body.append(e);
        }''', {'x': x, 'y': y, 'label': label})
        shot = await self.driver.screenshot('selection-preview')
        return {'ok': True, 'handle': handle, 'label': label, 'screenshot': str(shot),
                'confirmation_required': True, 'note': 'Marker previews a screen target, not proof of entity identity. Handles expire after view/geometry changes.'}

    async def edit(self, handle: str, operation: str, confirmed: bool = False, **args: Any) -> dict[str, Any]:
        if not confirmed:
            raise ValueError('Confirm the highlighted target before editing')
        target = self.selections.get(handle)
        if target is None:
            raise ValueError('Selection expired; select again from a fresh frame')
        await self._fresh(target['frame'])
        d = self.driver
        x, y = target['x'], target['y']
        if operation == 'dimension':
            value = float(args['value_mm'])
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Dimension must be positive and finite')
            await d.double_click(x, y)
            editor = d.page.locator('input.os-canvas-text-edit').first
            await editor.wait_for(state='visible', timeout=3000)
            old = await editor.input_value()
            await editor.fill(f'{value:g} mm')
            await d.press_key('Enter')
            await editor.wait_for(state='hidden', timeout=3000)
            result = {'ok': True, 'previous_value': old, 'requested_mm': value,
                      'verified': False, 'verification': 'pending_persisted_readback'}
        elif operation == 'add_dimension':
            value = float(args['value_mm'])
            if not math.isfinite(value) or value <= 0:
                raise ValueError('Dimension must be finite and positive')
            label = (float(args['label_x']), float(args['label_y']))
            size = await d.viewport_box()
            if not all(math.isfinite(v) for v in label) or not (0 <= label[0] < size['w'] and 0 <= label[1] < size['h']):
                raise ValueError('Dimension label must be inside the viewport')
            with ui_actions._px_space():
                result = (await ui_actions.sketch_dimension(d, (x, y), label, value)).to_dict()
        elif operation == 'constraint':
            points = [(x, y)]
            for other in args.get('handles', []):
                selected = self.selections.get(other)
                if not selected:
                    raise ValueError('Constraint target expired')
                await self._fresh(selected['frame'])
                points.append((selected['x'], selected['y']))
            with ui_actions._px_space():
                result = (await ui_actions.sketch_constrain(d, args['constraint_type'], *points)).to_dict()
            result['verified'] = False
        elif operation == 'move':
            end = (float(args['x']), float(args['y']))
            size = await d.viewport_box()
            if not all(math.isfinite(v) for v in end) or not (0 <= end[0] < size['w'] and 0 <= end[1] < size['h']):
                raise ValueError('Destination lies outside the viewport')
            await d.drag((x, y), end)
            result = {'ok': True, 'verified': False, 'verification': 'inspect_constraint_effects'}
        elif operation in ('delete', 'construction', 'trim', 'extend', 'split'):
            with ui_actions._px_space():
                if operation == 'delete':
                    await d.press_key('Escape')
                    await d.click(x, y)
                    await d.press_key('Delete')
                    result = {'ok': True, 'verified': False}
                else:
                    fn = getattr(ui_actions, 'sketch_' + operation)
                    result = (await fn(d, (x, y))).to_dict()
                    result['verified'] = False
        else:
            raise ValueError('Supported edits: dimension, add_dimension, constraint, move, delete, construction, trim, extend, split')
        self.selections.clear()
        return result

    async def next(self) -> dict[str, Any]:
        if not self.current or self.phase != 'ready' or self.pause_requested:
            raise ValueError('Request must be ready; resume a paused request first')
        run = self.current
        index = run['index']
        if index >= len(run['steps']):
            self.phase = run['status'] = 'complete'
            self.save()
            return {'ok': True, 'phase': self.phase, 'request': run}
        await self._fresh(run['after'])
        step = run['steps'][index]
        self.phase = run['status'] = 'running'
        self.save()  # A crash here records uncertain execution; begin never replays it.
        self.event('step_started', index=index, step=step)
        try:
            if step['tool'] == 'selection.edit':
                result = await self.edit(**step.get('args', {}))
            else:
                action_args = dict(step.get('args', {}))
                if step['tool'] in ('sketch.rectangle', 'sketch.circle'):
                    action_args['auto_dimension'] = False  # Never dimension two stale picks invisibly.
                raw = await dispatch(self.driver, step['tool'], action_args, space=step.get('space', 'px'))
                result = raw.to_dict() if hasattr(raw, 'to_dict') else raw
            if not isinstance(result, dict):
                result = {'ok': False, 'error': 'Action returned no structured evidence'}
        except Exception as exc:
            result = {'ok': False, 'error': str(exc), 'document_may_have_changed': True}
        run['index'] += 1  # Failed attempts are not implicitly replayed.
        run['results'].append(result)
        self.selections.clear()
        try:
            run['after'] = await self.observe()
        except Exception as exc:
            result.update(ok=False, observation_error=str(exc))
        result.setdefault('verified', False)
        self.phase = 'paused' if self.pause_requested or not result.get('ok') else (
            'complete' if run['index'] == len(run['steps']) else 'ready')
        run['status'] = self.phase
        self.save()
        self.event('step_finished', index=index, result=result, frame=run['after']['screenshot'])
        return {'ok': bool(result.get('ok')), 'phase': self.phase, 'index': index,
                'result': result, 'observation': run['after'], 'screenshot': run['after']['screenshot']}

    async def cancel(self) -> dict[str, Any]:
        self.pause_requested = True
        self.phase = 'cancelled'
        if self.current:
            self.current['status'] = self.phase
            self.save()
        self.selections.clear()
        self.event('cancel')
        return {'ok': True, 'phase': self.phase, 'note': 'Pending steps discarded; existing geometry retained. Use undo for a guarded rollback.'}

    async def undo(self) -> dict[str, Any]:
        run = self.current
        if not run or self.phase not in ('complete', 'cancelled', 'paused'):
            raise ValueError('Finish or pause the request before undo')
        if run['manual_handoff']:
            raise ValueError('Manual edits occurred during this request; use individual native undo with inspection')
        if not run['before']['model_digest'] or not run['after']['model_digest']:
            raise ValueError('Read-only model checkpoints are required for grouped undo')
        await self._fresh(run['after'])
        if run['before'].get('sketch_active') or run['after'].get('sketch_active'):
            raise ValueError('Grouped undo requires closed sketch checkpoints')
        # A committed sketch transaction is one native history operation. Arbitrary
        # action counts are NOT native undo counts; never guess and overshoot.
        tools = [s['tool'] for s in run['steps'][:run['index']]]
        if not tools or tools[0] not in ('sketch.start', 'feature.edit') or tools[-1] != 'sketch.exit':
            raise ValueError('Grouped undo requires one completed sketch edit transaction')
        if any(not t.startswith(('sketch.', 'view.', 'selection.')) or t in ('sketch.start', 'sketch.exit', 'sketch.create') for t in tools[1:-1]):
            raise ValueError('Multiple sketch transactions must be undone separately')
        if run['before']['model_digest'] == run['after']['model_digest']:
            raise ValueError('No persisted model change to undo')
        result = await ui_actions.doc_undo(self.driver)
        after = await self.observe()
        restored = bool(result.ok) and after['model_digest'] == run['before']['model_digest']
        self.phase = 'undone' if restored else 'paused'
        run['after'], run['status'] = after, self.phase
        self.save()
        self.selections.clear()
        self.event('undo', restored=restored, frame=after['screenshot'])
        return {'ok': restored, 'restored': restored, 'phase': self.phase, 'screenshot': after['screenshot'],
                'note': 'One native undo issued; checkpoint compared. No blind repeated undo.'}
