"""Presentation must distinguish injected faults, missing data and measured rest."""
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import build_run,catalog
from live_samples import chart_samples
from server import create_app,Controller
from test_server import FakePublisher


def points(**config):
    run=build_run({'duration_seconds':5,'include_samples':True,**config})
    return run,chart_samples(run['samples'])


@pytest.mark.parametrize('sensor',['thumb','palm','motion','contact'])
def test_targeted_fault_only_marks_selected_channel(sensor):
    run,data=points(mode='invalid',fault_sensor=sensor)
    assert all(p['sensor_states'][sensor]=='fault' for p in data)
    assert all(state not in ('fault','unknown') for p in data for key,state in p['sensor_states'].items() if key!=sensor)
    assert run['windows'][0]['quality']=='invalid'
    assert all(v is None for v in run['windows'][0]['metrics'].values())
    fault=next(e for e in run['events_expected'] if e['kind']=='sensor_fault')
    assert fault=={'kind':'sensor_fault','at_seconds':0,'sensors':[sensor],'origin':'computed'}
    assert not any(e['kind']=='sensor_fault' for w in run['windows'] for e in w['events'])
    assert run['provenance']['fault_sensor']==sensor
    json.dumps(data,allow_nan=False)


def test_legacy_fault_keeps_contact_and_replay_missing_is_not_a_fault():
    _,data=points(mode='invalid')
    assert all(p['sensor_states']=={'thumb':'fault','palm':'fault','motion':'fault','contact':'active'} for p in data)
    _,data=points(source='phyphox',dataset_id='usage')
    assert all(p['sensor_states']['thumb']=='unknown' and p['sensor_states']['contact']=='unknown' for p in data)
    assert all('fault' not in p['sensor_states'].values() for p in data)
    assert all(p['contact_seconds'] is None and p['quiet_seconds'] is None for p in data)
    assert any(p['sensor_states']['motion']=='active' for p in data)


def test_states_and_timers_follow_engine_not_a_ui_clock():
    run,data=points(mode='normal',duration_seconds=15)
    assert data[0]['sensor_states']['thumb']=='active'
    at_rest=next(p for p in data if p['time_seconds']==9)
    assert at_rest['sensor_states']['thumb']=='rest'
    assert at_rest['sensor_states']['contact']=='rest'
    assert at_rest['sensor_states']['motion']=='rest'
    _,data=points(mode='force',duration_seconds=10)
    assert data[0]['sensor_states']['thumb']=='high'
    assert not data[0]['flags']['high_force']
    assert data[-1]['flags']['high_force']
    run,data=points(mode='immobile',duration_seconds=20)
    quiet=next(p for p in data if p['time_seconds']==10)
    assert quiet['quiet_seconds']==pytest.approx(10.05)
    assert quiet['flags']['quiet_contact']
    assert data[-1]['flags']['absent']
    assert data[-1]['sensor_states']['contact']=='rest'


def test_gap_hides_timers_and_activity_instead_of_showing_rest():
    run,_=points(mode='normal')
    row=run['samples'][4]
    row['dt_seconds']=.3
    point=chart_samples([row])[0]
    assert set(point['sensor_states'].values())=={'unknown'}
    assert point['contact_seconds'] is None and point['quiet_seconds'] is None
    assert point['motion_active'] is None and not any(point['flags'].values())


def test_visual_faults_are_never_sent_as_usage_alerts(tmp_path):
    pub=FakePublisher()
    controller=Controller(build_run,pub,tmp_path)
    plan=controller.prepare({'source':'wokwi','mode':'invalid','fault_sensor':'thumb','duration_seconds':5})
    assert any(e['kind']=='sensor_fault' for e in plan['events_expected'])
    assert all(w['events_to_send']==[] for w in plan['windows'])
    assert pub.packets==[] and pub.connections==0


def test_api_validates_targeted_fault_and_preview_is_side_effect_free(tmp_path):
    pub=FakePublisher()
    with TestClient(create_app(build_run,catalog,pub,tmp_path),base_url='http://127.0.0.1:8774') as client:
        token=client.get('/api/state').json()['csrf_token']
        client.headers.update({'origin':'http://127.0.0.1:8774','x-csrf-token':token})
        for cfg in ({'fault_sensor':'fake'},{'fault_sensor':'thumb'},{'source':'phyphox','mode':'invalid','fault_sensor':'thumb'}):
            assert client.post('/api/preview',json=cfg).status_code==422
        response=client.post('/api/preview',json={'mode':'invalid','fault_sensor':'contact','duration_seconds':5})
        assert response.status_code==200
        assert response.json()['chart_samples'][0]['sensor_states']['contact']=='fault'
        assert pub.packets==[] and pub.connections==0


@pytest.mark.parametrize('cfg',[{'fault_sensor':'fake'},{'fault_sensor':'thumb'},{'source':'phyphox','mode':'invalid','fault_sensor':'thumb'}])
def test_engine_also_rejects_invalid_fault_configuration(cfg):
    with pytest.raises(ValueError):build_run(cfg)
