import json
from pathlib import Path
import sys
import time
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import create_app,Controller


class FakePublisher:
    def __init__(self):
        self.connected=False;self.packets=[];self.connections=0
        self.meta={'device_id':'demo-device-a','firmware_version':'test','algorithm_version':'test','calibration_version':'test','calibration_status':'synthetic_reference'}
    def connect(self):self.connected=True;self.connections+=1
    def close(self):self.connected=False
    def status(self):return {'configured':True,'connected':self.connected,'device_id':'demo-device-a'}
    def send(self,packet):self.packets.append(packet)


def plan(config):
    invalid=config.get('mode')=='invalid'
    return {'windows':[{'index':0,'start_seconds':0,'end_seconds':5,'duration_seconds':.15,'quality':'invalid' if invalid else 'valid',
                        'metrics':dict.fromkeys(('contact_seconds','episodes','thumb_pct','palm_pct')) if invalid else {'contact_seconds':.1,'episodes':1,'thumb_pct':10.,'palm_pct':20.},
                        'publish':config.get('mode')!='network_cut','events':[]}],
            'summary':{'expected':True},'provenance':{'synthetic':True},'events_expected':[]}


@pytest.fixture
def bank(tmp_path):
    publisher=FakePublisher();app=create_app(plan,lambda:{'modes':[]},publisher,tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8774') as client:
        csrf=client.get('/api/state').json()['csrf_token']
        client.headers.update({'origin':'http://127.0.0.1:8774','x-csrf-token':csrf})
        yield client,publisher,app.state.controller,tmp_path


def wait_finished(controller):
    controller.thread.join(timeout=2)
    assert not controller.thread.is_alive()
    return controller.snapshot()


def test_preview_never_sends_and_no_browser_target_override(bank):
    client,publisher,_,_=bank
    assert client.post('/api/preview',json={'duration_seconds':5}).status_code==200
    assert publisher.connections==0 and publisher.packets==[]
    for forbidden in ({'device_id':'another'},{'source':'filesystem','dataset_id':'../../secret'},{'duration_seconds':10000},{'duration_seconds':True}):
        assert client.post('/api/start',json=forbidden).status_code==422


def test_cross_origin_csrf_host_and_cache_boundaries(bank):
    client,publisher,_,_=bank
    assert client.post('/api/start',json={},headers={'origin':'https://attacker.invalid'}).status_code==403
    assert client.post('/api/start',json={},headers={'x-csrf-token':'bad'}).status_code==403
    assert client.get('/api/state',headers={'host':'attacker.invalid'}).status_code==400
    response=client.get('/api/state')
    assert response.headers['cache-control']=='no-store' and 'access-control-allow-origin' not in response.headers
    assert publisher.connections==0


@pytest.mark.parametrize('mode',['normal','invalid','network_cut'])
def test_real_time_packet_contract_and_honest_receipt(bank,mode):
    client,publisher,controller,folder=bank
    assert client.post('/api/start',json={'duration_seconds':5,'mode':mode}).status_code==200
    assert client.post('/api/start',json={'duration_seconds':5}).status_code==409
    state=wait_finished(controller)
    assert state['status']=='completed' and state['report_available']
    saved=json.loads((folder/(state['run_id']+'.json')).read_text())
    assert saved['provenance']['synthetic'] is True
    if mode=='network_cut':assert publisher.packets==[] and state['skipped_windows']==1
    else:
        packet=publisher.packets[0]
        assert packet['session_id']==state['run_id'] and packet['synthetic'] is True
        assert packet['window_start']<packet['measured_at'] and packet['device_id']=='demo-device-a'
        assert state['windows'][0]['delivery']=='broker_accepted'
        assert 'database_confirmed' not in state
        if mode=='invalid':assert packet['metrics'] is None
        else:assert packet['metrics']['episodes']==1
    assert client.get('/api/report').status_code==200


def test_pause_discards_partial_window_stop_does_not_publish(bank):
    client,publisher,controller,_=bank
    client.post('/api/start',json={'duration_seconds':5})
    assert client.post('/api/pause',json={}).status_code==200
    time.sleep(.2)
    assert publisher.packets==[] and controller.snapshot()['progress_seconds']==0
    assert client.post('/api/resume',json={}).status_code==200
    assert client.post('/api/stop',json={}).status_code==200
    assert wait_finished(controller)['status']=='stopped'
    assert publisher.packets==[]


def test_unverified_calibration_cannot_send_valid_metrics(bank):
    client,publisher,controller,_=bank
    publisher.meta['calibration_status']='required'
    client.post('/api/start',json={'duration_seconds':5})
    state=wait_finished(controller)
    assert publisher.packets[0]['quality']=='calibration_required'
    assert publisher.packets[0]['metrics'] is None
    assert state['windows'][0]['computed_quality']=='valid'
    assert state['windows'][0]['quality']=='calibration_required'


def test_selected_computed_events_are_offsets_not_run_times(tmp_path):
    def event_plan(config):
        result=plan(config)
        result['windows'][0].update(start_seconds=10,end_seconds=15,events=[
            {'kind':'high_force','at_seconds':10.05}, {'kind':'quiet_contact','at_seconds':10.1}])
        return result
    publisher=FakePublisher()
    controller=Controller(event_plan,publisher,tmp_path)
    config={'source':'wokwi','mode':'normal','duration_seconds':5,'event_kinds':['high_force']}
    preview=controller.prepare(config)
    assert len(preview['windows'][0]['events_to_send'])==1
    assert publisher.packets==[]
    controller.start(config);wait_finished(controller)
    assert publisher.packets[0]['events']==[{'kind':'high_force','at_seconds':.05,'origin':'computed'}]


def test_explicit_event_queues_once_and_keeps_manual_origin(bank):
    client,publisher,controller,_=bank
    assert client.post('/api/events',json={'kind':'high_force'}).status_code==409
    client.post('/api/start',json={'duration_seconds':5,'event_kinds':[]})
    assert client.post('/api/events',json={'kind':'high_force'}).json()['status']=='queued'
    assert client.post('/api/events',json={'kind':'high_force'}).status_code==409
    assert client.post('/api/events',json={'kind':'intrusion'}).status_code==422
    assert client.post('/api/events',json={'kind':'absent'},headers={'origin':'https://attacker.invalid'}).status_code==403
    state=wait_finished(controller)
    event=publisher.packets[0]['events'][0]
    assert event['kind']=='high_force' and event['origin']=='manual'
    assert 0<=event['at_seconds']<=.15
    assert state['pending_events']==[]


@pytest.mark.parametrize('mode',['invalid','network_cut'])
def test_events_cannot_override_invalid_quality_or_network_cut(bank,mode):
    client,publisher,controller,_=bank
    client.post('/api/start',json={'duration_seconds':5,'mode':mode})
    assert client.post('/api/events',json={'kind':'high_force'}).status_code==409
    wait_finished(controller)
    assert not publisher.packets or not publisher.packets[0].get('events')


def test_selected_event_schema_is_closed_and_cannot_duplicate(bank):
    client,*_=bank
    for kinds in (['high_force','high_force'],['intrusion'],['pause_reminder']*5):
        assert client.post('/api/preview',json={'event_kinds':kinds}).status_code==422


def test_manual_event_retains_evidence_when_puback_fails(bank):
    from transport import TransportUnavailable
    client,publisher,controller,_=bank
    def fail(packet):raise TransportUnavailable('Accusé absent')
    publisher.send=fail
    client.post('/api/start',json={'duration_seconds':5,'event_kinds':[]})
    client.post('/api/events',json={'kind':'high_force'})
    state=wait_finished(controller)
    assert state['status']=='failed' and state['broker_accepted']==0
    assert state['windows'][0]['delivery']=='delivery_unknown'
    assert state['windows'][0]['events_attempted'][0]['origin']=='manual'
    assert state['windows'][0]['events_sent']==[]


def test_manual_event_waits_through_invalid_window(tmp_path):
    def mixed(config):
        result=plan(config)
        invalid=plan({'mode':'invalid'})['windows'][0]
        result['windows'].insert(0,invalid)
        return result
    publisher=FakePublisher();controller=Controller(mixed,publisher,tmp_path)
    controller.start({'source':'wokwi','mode':'normal','duration_seconds':10})
    controller.enqueue_event('absent')
    state=wait_finished(controller)
    assert not publisher.packets[0].get('events')
    assert publisher.packets[1]['events'][0]['kind']=='absent'
    assert state['cancelled_events']==[]


def test_event_requested_after_interval_end_is_not_backdated(bank):
    client,publisher,controller,_=bank
    client.post('/api/start',json={'duration_seconds':5,'event_kinds':[]})
    with controller.lock:
        controller.pending_events['absent']=time.time()+30
    state=wait_finished(controller)
    assert publisher.packets[0]['events']==[]
    assert state['cancelled_events']==['absent']


def test_local_mode_has_no_network_and_keeps_manual_event(bank):
    client,publisher,controller,_=bank
    publisher.meta['calibration_status']='required'
    client.post('/api/start',json={'duration_seconds':5,'delivery_mode':'local'})
    assert client.post('/api/events',json={'kind':'high_force'}).status_code==200
    state=wait_finished(controller)
    assert publisher.connections==0 and publisher.packets==[] and state['broker_accepted']==0
    assert state['windows'][0]['delivery']=='local_only'
    assert state['detected_events'][0]['origin']=='manual'
