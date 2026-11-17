"""Compatibility of the public launcher catalogue with the existing domain API."""
import json
from pathlib import Path
import sys

import pytest

SIMULATOR = Path(__file__).resolve().parents[1]
APPLICATION = SIMULATOR.parent / 'application'
sys.path.insert(0, str(SIMULATOR))
sys.path.insert(0, str(APPLICATION))

from actions_catalog import catalog
from app.domain import SCHEMAS


def sample_payload(action):
    payload = dict(action.get('fixed_payload', {}))
    for field in action['fields']:
        if not field['required']:
            continue
        if field.get('default') == 'today' and field['type'] == 'date':
            value = '2026-11-15'
        elif 'default' in field:
            value = field['default']
        elif field.get('options'):
            value = field['options'][0]['value']
        elif field['type'] == 'boolean':
            value = False
        elif field['type'] == 'integer':
            value = field.get('min', 1)
        else:
            value = 'demo-reference'
        parts = field.get('payload_path', [field['name']])
        target = payload
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = value
    return payload


def test_catalog_covers_all_existing_commands_without_new_execution_endpoint():
    actions = catalog()['actions']
    commands = {a['action'] for a in actions if a['method'] == 'POST'}
    assert commands == set(SCHEMAS)
    for action in actions:
        assert action['method'] in {'GET', 'POST'}
        assert action['path'] == ('/api/actions' if action['method'] == 'POST' else '/api/export')
    exports = [a for a in actions if a['method'] == 'GET']
    assert {(a['fixed_payload']['kind'], tuple(a['roles'])) for a in exports} == {
        ('personal', ('user',)), ('prevention', ('employer',))}


@pytest.mark.parametrize('action', [a for a in catalog()['actions'] if a['method'] == 'POST'], ids=lambda a: a['id'])
def test_generated_payload_and_optional_fields_match_strict_domain_schema(action):
    model = SCHEMAS[action['action']]
    model.model_validate(sample_payload(action))
    paths = {f.get('payload_path', [f['name']])[0] for f in action['fields']}
    assert paths <= set(model.model_fields)
    required = {name for name, f in model.model_fields.items() if f.is_required()}
    assert required <= paths


def test_workflows_preserve_persona_boundaries_and_have_no_automatic_chain():
    content = catalog()
    actions = {a['id']: a for a in content['actions']}
    assert len(actions) == len(content['actions'])
    for workflow in content['workflows']:
        assert workflow['steps']
        for step in workflow['steps']:
            assert step['role'] in actions[step['action_id']]['roles']
            assert set(step) == {'action_id', 'role', 'label'}
    for action in actions.values():
        assert 'auto_execute' not in action
        assert action['description'] and action['effect']
    # The employer role was explicitly excluded from session management and health export.
    assert 'employer' not in actions['session.revoke']['roles']
    assert 'clinician' not in actions['export.personal']['roles']
    for action in actions.values():
        if action['action'] == 'settings.save' and set(action['roles']) - {'user'}:
            assert {f['name'] for f in action['fields']} <= {'large_text', 'high_contrast'}


def test_destructive_or_evidence_actions_do_not_contain_prevalidated_success():
    actions = {a['id']: a for a in catalog()['actions']}
    for name in ['device.calibrate', 'device.update', 'device.replace', 'certificate.request', 'account.approve', 'deletion.review', 'ticket.status', 'incident.close']:
        assert actions[name]['limitations']
    assert not any(f.get('default') for f in actions['ticket.checks']['fields'] if f['type'] == 'boolean')
    assert 'default' not in next(f for f in actions['incident.close']['fields'] if f['name'] == 'proof')
    assert 'default' not in next(f for f in actions['patch.evaluate']['fields'] if f['name'] == 'tests')


def test_static_copy_is_identical_and_dates_are_not_frozen():
    exported = json.loads((APPLICATION / 'app/static/simulation-catalog.json').read_text(encoding='utf-8'))
    assert exported == catalog()
    for action in exported['actions']:
        for field in action['fields']:
            if field['type'] == 'date':
                assert field.get('default') == 'today'
    altered = catalog()
    altered['actions'][0]['roles'].append('untrusted')
    assert altered != catalog()
