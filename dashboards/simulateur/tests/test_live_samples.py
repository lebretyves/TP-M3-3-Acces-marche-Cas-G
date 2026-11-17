import math
import sys
from pathlib import Path
import time
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import build_run,catalog
from live_samples import chart_samples,MAX_POINTS
from server import create_app
from test_server import FakePublisher


def test_chart_values_come_from_engine_and_do_not_turn_missing_into_zero():
    normal=build_run({'mode':'normal','duration_seconds':5,'include_samples':True})
    points=chart_samples(normal['samples'])
    assert points[0]['thumb_pct']==normal['samples'][0]['thumb_pct']
    assert any(p['gyro_norm']>0 for p in points)
    invalid=chart_samples(build_run({'mode':'invalid','duration_seconds':5,'include_samples':True})['samples'])
    assert all(p['thumb_pct'] is None and p['palm_pct'] is None and p['gyro_norm'] is None for p in invalid)
    replay=chart_samples(build_run({'source':'phyphox','dataset_id':'usage','duration_seconds':5,'include_samples':True})['samples'])
    assert all(p['contact'] is None and p['thumb_pct'] is None for p in replay)
    assert any(p['gyro_norm'] is not None for p in replay)


def test_gap_and_nonfinite_values_are_missing_and_response_is_bounded():
    row={'time_seconds':0.,'sample':{'thumbValid':True,'palmValid':True,'motionValid':True,'contactValid':True,'contact':True},'dt_seconds':.3,'gyro_norm':math.nan,'thumb_pct':20.,'palm_pct':30.,'valid':False}
    point=chart_samples([row])[0]
    assert all(point[k] is None for k in ('thumb_pct','palm_pct','gyro_norm','contact'))
    assert len(chart_samples([row]*(MAX_POINTS*3+1)))<=MAX_POINTS


def test_decimation_preserves_a_gap_between_selected_points():
    rows=[{'time_seconds':i*.05,'sample':{'thumbValid':True,'palmValid':True,'motionValid':True,'contactValid':True,'contact':True},'dt_seconds':.05,'gyro_norm':.1,'thumb_pct':20.,'palm_pct':30.,'valid':True} for i in range(MAX_POINTS*2)]
    rows[1]['dt_seconds']=.3  # stride 2 would otherwise discard this hole.
    points=chart_samples(rows)
    assert points[0]['gyro_norm']==.1
    assert points[1]['time_seconds']==.1 and points[1]['gyro_norm'] is None
    assert points[1]['contact'] is None and points[1]['thumb_pct'] is None
    assert points[2]['gyro_norm']==.1


def test_running_chart_does_not_reveal_future_or_count_pause(tmp_path):
    pub=FakePublisher();app=create_app(build_run,catalog,pub,tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8774') as client:
        token=client.get('/api/state').json()['csrf_token']
        client.headers.update({'origin':'http://127.0.0.1:8774','x-csrf-token':token})
        assert client.post('/api/start',json={'duration_seconds':5,'delivery_mode':'local'}).status_code==200
        time.sleep(.25)
        state=client.get('/api/state').json()['state']
        assert 0<state['elapsed_seconds']<1
        assert state['chart_samples'] and all(p['time_seconds']<state['elapsed_seconds'] for p in state['chart_samples'])
        assert pub.connections==0 and pub.packets==[]
        client.post('/api/pause',json={});time.sleep(.2)
        paused=client.get('/api/state').json()['state']
        assert paused['elapsed_seconds']==0 and paused['chart_samples']==[]
        client.post('/api/stop',json={})


def test_proxy_origin_allowed_but_other_origins_denied(tmp_path):
    app=create_app(build_run,catalog,FakePublisher(),tmp_path)
    with TestClient(app,base_url='http://localhost:8443') as client:
        token=client.get('/api/state').json()['csrf_token']
        headers={'origin':'https://localhost:8443','x-csrf-token':token}
        response=client.post('/api/preview',json={'duration_seconds':5},headers=headers)
        assert response.status_code==200 and response.json()['chart_samples']
        headers['origin']='https://attacker.invalid'
        assert client.post('/api/preview',json={},headers=headers).status_code==403


def test_loopback_entry_redirects_but_proxied_entry_stays_inline(tmp_path,monkeypatch):
    monkeypatch.setenv('SIMULATOR_PUBLIC_URL','https://localhost:8443/simulateur/')
    app=create_app(build_run,catalog,FakePublisher(),tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8774') as client:
        redirect=client.get('/',follow_redirects=False)
        assert redirect.status_code==307 and redirect.headers['location']=='https://localhost:8443/simulateur/'
        assert client.get('/',headers={'x-forwarded-prefix':'/simulateur'}).status_code==200
