"""Read-only sketch inventory and exact persisted-dimension verification.

No feature creation, FeatureScript, or API writes are performed here.
Uncommitted UI edits may not be represented in the feature response.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

from .onshape_api import _message, document_ref, request


def millimetres(expression: str) -> float | None:
    """Only literal lengths; expressions/variables need a solver readback."""
    match = re.fullmatch(r'\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(mm|cm|m|in|inch)\s*', expression)
    if not match:
        return None
    value = float(match[1]) * {'mm': 1, 'cm': 10, 'm': 1000, 'in': 25.4, 'inch': 25.4}[match[2]]
    return value if math.isfinite(value) else None


def canonical_features(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [_message(f) for f in payload.get('features', [])]


def fingerprint(payload: dict[str, Any]) -> str:
    # Exclude microversion: native undo changes it even when restoring geometry.
    data = {'features': canonical_features(payload), 'featureStates': payload.get('featureStates', {})}
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inventory(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        'feature_id': f.get('featureId'), 'name': f.get('name'),
        'type': f.get('featureType'),
        'entities': [_message(e) for e in f.get('entities', [])],
        'constraints': [_message(c) for c in f.get('constraints', [])],
        'status': payload.get('featureStates', {}).get(f.get('featureId')),
    } for f in canonical_features(payload)]


async def read_features(driver: Any) -> dict[str, Any]:
    did, wvm, ident, eid = document_ref(driver.page.url)
    return await request(driver, 'GET',
        f'/api/v9/partstudios/d/{did}/{wvm}/{ident}/e/{eid}/features'
        '?rollbackBarIndex=-1&includeGeometryIds=true&noSketchGeometry=false')


def verify_dimension(payload: dict[str, Any], feature_id: str, constraint_id: str,
                     value_mm: float, tolerance_mm: float = 0.001) -> dict[str, Any]:
    if not math.isfinite(value_mm) or not math.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError('Dimension and tolerance must be finite; tolerance must be positive')
    feature = next((f for f in canonical_features(payload) if f.get('featureId') == feature_id), None)
    if feature is None:
        return {'ok': False, 'verified': False, 'reason': 'feature_not_found'}
    constraint = next((_message(c) for c in feature.get('constraints', [])
                       if _message(c).get('constraintId') == constraint_id), None)
    if constraint is None:
        return {'ok': False, 'verified': False, 'reason': 'constraint_not_found'}
    params = [_message(p) for p in constraint.get('parameters', [])]
    lengths = [p for p in params if p.get('parameterId') in ('length', 'diameter', 'radius', 'distance')]
    if len(lengths) != 1:
        return {'ok': False, 'verified': False, 'reason': 'ambiguous_or_unsupported_dimension'}
    actual = millimetres(str(lengths[0].get('expression', '')))
    state = _message(payload.get('featureStates', {}).get(feature_id, {})).get('featureStatus')
    verified = actual is not None and abs(actual - value_mm) <= tolerance_mm and state == 'OK'
    return {'ok': verified, 'verified': verified, 'requested_mm': value_mm,
            'actual_mm': actual, 'feature_status': state, 'constraint_id': constraint_id,
            'reason': 'verified_persisted_constraint' if verified else 'value_or_solver_state_unverified'}
