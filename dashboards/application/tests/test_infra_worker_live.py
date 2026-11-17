"""Explicit synthetic end-to-end test: real MQTT worker + PostgreSQL service role."""
import json
import os
from pathlib import Path
import ssl
import threading
import time
from datetime import datetime,timezone
from uuid import uuid4
import paho.mqtt.client as mqtt
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
import pytest
from app.models import Report
from app.domain_models import DomainJob,DomainRecord
from app.transport_models import IngestReceipt,IngestDeviceCursor

pytestmark=pytest.mark.skipif(os.getenv('SKELIVIA_LIVE_WORKER')!='1',reason='Explicit dedicated PostgreSQL/MQTT test only')


def test_worker_live():
    engine=create_engine(Path('/run/owner_database_url').read_text().strip(),hide_parameters=True)
    sessions=sessionmaker(engine,expire_on_commit=False)
    session_id=str(uuid4());job_id='live-cal-'+uuid4().hex
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='live-device-'+uuid4().hex,protocol=mqtt.MQTTv5)
    tls=ssl.create_default_context(cafile='/pki/ca.pem');tls.load_cert_chain('/device/cert.pem','/device/key.pem');client.tls_set_context(tls)
    ready=threading.Event();received=threading.Event();commands=[]
    def connected(c,u,f,r,p):
        assert not r.is_failure;c.subscribe('skelivia/v1/devices/skm-001/commands',qos=1);ready.set()
    def message(c,u,m):
        obj=json.loads(m.payload)
        if obj.get('job_id')==job_id:commands.append(obj);received.set()
    client.on_connect=connected;client.on_message=message
    client.connect('broker',8883);client.loop_start();assert ready.wait(5)
    try:
        with sessions() as db:
            device=db.get(DomainRecord,'demo-device-a');calibration=device.data['calibration'];usable=device.data['calibration_status']=='synthetic_reference'
            cursor=db.get(IngestDeviceCursor,'demo-device-a');start=max(time.time()-30,cursor.last_window_end if cursor else 0)
        end=time.time();duration=end-start
        packet={'schema_version':'skelivia.telemetry.v1','synthetic':True,'device_id':'demo-device-a','session_id':session_id,'sequence':1,'measured_at':datetime.fromtimestamp(end,timezone.utc).isoformat(),'window_start':datetime.fromtimestamp(start,timezone.utc).isoformat(),'firmware_version':'2.4.1','algorithm_version':'1.0','calibration_version':calibration,'quality':'valid' if usable else 'calibration_required','metrics':{'contact_seconds':min(12.0,duration/2),'episodes':3,'thumb_pct':20.0,'palm_pct':30.0} if usable else None}
        client.publish('skelivia/v1/devices/skm-001/telemetry',json.dumps(packet),qos=1).wait_for_publish(5)
        deadline=time.time()+10;receipt=None
        while time.time()<deadline:
            with sessions() as db:receipt=db.scalar(select(IngestReceipt).where(IngestReceipt.session_id==session_id))
            if receipt:break
            time.sleep(.2)
        assert receipt,'Worker did not persist a fresh valid telemetry packet'
        with sessions() as db:assert db.get(Report,receipt.report_id).patient_id=='p-alice'
        replay_session=str(uuid4());replay={**packet,'session_id':replay_session,'sequence':99}
        client.publish('skelivia/v1/devices/skm-001/telemetry',json.dumps(replay),qos=1).wait_for_publish(5)
        time.sleep(.5)
        with sessions() as db:assert db.scalar(select(IngestReceipt).where(IngestReceipt.session_id==replay_session)) is None,'Changing session replayed an already counted interval'
        now=time.time()
        with sessions.begin() as db:db.add(DomainJob(id=job_id,kind='calibration',target_id='demo-device-a',owner_id='u-alice',status='pending',payload={'device_id':'demo-device-a'},result={},created_at=now,updated_at=now))
        assert received.wait(10),'Worker did not dispatch command with PostgreSQL role'
        cmd=commands[0]
        ack={'schema_version':'skelivia.ack.v1','synthetic':True,'job_id':job_id,'device_id':'demo-device-a','kind':'calibration','nonce':'0'*64,'status':'succeeded','proof_id':str(uuid4()),'measured_at':datetime.now(timezone.utc).isoformat(),'calibration_version':'C-LIVE-BANK'}
        client.publish('skelivia/v1/devices/skm-001/ack',json.dumps(ack),qos=1).wait_for_publish(5)
        time.sleep(.5)
        with sessions() as db:assert db.get(DomainJob,job_id).status=='sent','Forged nonce changed job state'
        ack['nonce']=cmd['nonce']
        client.publish('skelivia/v1/devices/skm-001/ack',json.dumps(ack),qos=1).wait_for_publish(5)
        deadline=time.time()+10;status=None
        while time.time()<deadline:
            with sessions() as db:status=db.get(DomainJob,job_id).status
            if status=='completed':break
            time.sleep(.2)
        assert status=='completed','Authenticated ACK did not complete synthetic job'
        with sessions() as db:
            device=db.get(DomainRecord,'demo-device-a')
            assert device.data['calibration_status']=='synthetic_reference'
            assert device.data['calibration']=='C-LIVE-BANK'
        print(json.dumps({'postgres_worker_ingestion':'PASS','cross_session_interval_replay_rejected':'PASS','mqtt_command_dispatch':'PASS','forged_nonce_rejected':'PASS','authenticated_ack':'PASS','physical_calibration_claim':False}))
    finally:client.disconnect();client.loop_stop();engine.dispose()


def test_signed_update_live():
    from app.domain_models import DomainDiagnostic
    engine=create_engine(Path('/run/owner_database_url').read_text().strip(),hide_parameters=True)
    sessions=sessionmaker(engine,expire_on_commit=False)
    job_id='live-update-'+uuid4().hex;ready=threading.Event();received=threading.Event();commands=[]
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='live-update-'+uuid4().hex,protocol=mqtt.MQTTv5)
    tls=ssl.create_default_context(cafile='/pki/ca.pem');tls.load_cert_chain('/device/cert.pem','/device/key.pem');client.tls_set_context(tls)
    def connected(c,u,f,r,p):
        assert not r.is_failure;c.subscribe('skelivia/v1/devices/skm-001/commands',qos=1);ready.set()
    def message(c,u,m):
        obj=json.loads(m.payload)
        if obj.get('job_id')==job_id:commands.append(obj);received.set()
    client.on_connect=connected;client.on_message=message
    original_diagnostic=None;original_status=None
    try:
        client.connect('broker',8883);client.loop_start();assert ready.wait(5)
        with sessions.begin() as db:
            patch=db.get(DomainRecord,'patch-demo');original_status=patch.status;patch.status='approved'
            diagnostic=db.get(DomainDiagnostic,'ticket-alice')
            if diagnostic:
                original_diagnostic={key:getattr(diagnostic,key) for key in ('ticket_id','device_id','support_id','owner_id','expires','active')}
                diagnostic.active=True;diagnostic.expires=time.time()+120
            else:db.add(DomainDiagnostic(ticket_id='ticket-alice',device_id='demo-device-a',support_id='t-support',owner_id='u-alice',expires=time.time()+120,active=True))
            db.add(DomainJob(id=job_id,kind='update',target_id='demo-device-a',owner_id='u-alice',assigned_to='t-support',status='pending',payload={'device_id':'demo-device-a','ticket_id':'ticket-alice','patch_id':'patch-demo','version':'2.4.2'},result={},created_at=time.time(),updated_at=time.time()))
        assert received.wait(10),'Signed update was not dispatched with PostgreSQL role'
        command=commands[0];assert command['artifact']['synthetic'] is True
        ack={'schema_version':'skelivia.ack.v1','synthetic':True,'job_id':job_id,'device_id':'demo-device-a','kind':'update','nonce':command['nonce'],'status':'succeeded','proof_id':str(uuid4()),'measured_at':datetime.now(timezone.utc).isoformat(),'firmware_version':'2.4.2','artifact_sha256':command['artifact']['sha256']}
        client.publish('skelivia/v1/devices/skm-001/ack',json.dumps(ack),qos=1).wait_for_publish(5)
        deadline=time.time()+10;status=None
        while time.time()<deadline:
            with sessions() as db:status=db.get(DomainJob,job_id).status
            if status=='completed':break
            time.sleep(.2)
        assert status=='completed','Signed update ACK did not complete'
        with sessions() as db:
            data=db.get(DomainRecord,'demo-device-a').data
            assert data['firmware']=='2.4.2' and data['calibration_status']=='required'
        print(json.dumps({'postgres_signed_update_dispatch':'PASS','approved_patch_and_temporary_diagnostic':'PASS','digest_bound_ack':'PASS','physical_firmware_flash':False}))
    finally:
        client.disconnect();client.loop_stop()
        if original_status is not None:
            with sessions.begin() as db:
                db.get(DomainRecord,'patch-demo').status=original_status
                diagnostic=db.get(DomainDiagnostic,'ticket-alice')
                if original_diagnostic:
                    for key,value in original_diagnostic.items():setattr(diagnostic,key,value)
                elif diagnostic:db.delete(diagnostic)
        engine.dispose()


def test_concurrent_intervals_live():
    from concurrent.futures import ThreadPoolExecutor
    from app.ingestion import ingest,IngestionRejected
    owner_engine=create_engine(Path('/run/owner_database_url').read_text().strip(),hide_parameters=True)
    owner=sessionmaker(owner_engine,expire_on_commit=False)
    worker_engine=create_engine(Path('/run/worker_database_url').read_text().strip(),hide_parameters=True)
    worker=sessionmaker(worker_engine,expire_on_commit=False)
    with owner() as db:
        cursor=db.get(IngestDeviceCursor,'demo-device-a');start=max(time.time()-30,cursor.last_window_end if cursor else 0)
        calibration=db.get(DomainRecord,'demo-device-a').data['calibration']
    now=datetime.now(timezone.utc)
    def attempt(_):
        packet={'schema_version':'skelivia.telemetry.v1','synthetic':True,'device_id':'demo-device-a','session_id':str(uuid4()),'sequence':1,'window_start':datetime.fromtimestamp(start,timezone.utc).isoformat(),'measured_at':now.isoformat(),'firmware_version':'2.4.2','algorithm_version':'1.0','calibration_version':calibration,'quality':'calibration_required','metrics':None}
        try:ingest(worker,'skelivia/v1/devices/skm-001/telemetry',json.dumps(packet).encode(),now=now);return 'accepted'
        except IngestionRejected as error:return str(error)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,range(2)))
        assert sorted(results)==['accepted','overlapping_interval'],results
        print('{"postgres_concurrent_interval_serialization":"PASS"}')
    finally:owner_engine.dispose();worker_engine.dispose()


if __name__=='__main__':
    test_worker_live()
    test_signed_update_live()
    test_concurrent_intervals_live()
