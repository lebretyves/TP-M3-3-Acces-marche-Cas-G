import base64
from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.models import Base, Report
from app.domain_models import DomainRecord
from app.transport_models import DeviceIdentity, IngestCursor, IngestReceipt
from app.ingestion import ingest, IngestionRejected

NOW = datetime(2026,11,14,12,0,tzinfo=timezone.utc)
TOPIC = 'skelivia/v1/devices/skm-001/telemetry'


@pytest.fixture
def bank(tmp_path,monkeypatch):
    key=tmp_path/'key'; key.write_bytes(base64.b64encode(b'x'*32))
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(key))
    engine=create_engine('sqlite:///'+str(tmp_path/'ingest.db'))
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory.begin() as db:
        db.add(DeviceIdentity(cert_cn='skm-001',device_id='demo-device-a',cert_serial='123'))
        db.add(DomainRecord(id='demo-device-a',kind='device',owner_id='u-alice',patient_id='p-alice',status='active',data={'calibration':'C-DEMO-01','calibration_status':'synthetic_reference','certificate':{'serial':'123','revoked':False}},created_at=0,updated_at=0))
    yield factory
    engine.dispose()


def packet(**overrides):
    data={'schema_version':'skelivia.telemetry.v1','synthetic':True,'device_id':'demo-device-a','session_id':str(uuid4()),'sequence':1,'measured_at':NOW.isoformat(),'window_start':(NOW-timedelta(seconds=60)).isoformat(),'firmware_version':'2.4.1','algorithm_version':'1.0','calibration_version':'C-DEMO-01','quality':'valid','metrics':{'contact_seconds':60.0,'episodes':8,'thumb_pct':20.0,'palm_pct':30.0}}
    data.update(overrides)
    return json.dumps(data).encode()


def test_persists_derived_report_encrypted_and_binds_patient(bank):
    report_id=ingest(bank,TOPIC,packet(),now=NOW)
    with bank() as db:
        report=db.get(Report,report_id)
        assert report.patient_id=='p-alice' and report.synthetic is True
        assert report.metrics['contact_seconds']==60
        assert db.scalar(select(IngestReceipt)).report_id==report_id
        from sqlalchemy import text
        raw=db.execute(text('SELECT metrics FROM reports')).scalar_one()
        assert raw.startswith('v1:') and 'contact_seconds' not in raw


@pytest.mark.parametrize('change',[
    {'synthetic':False},{'synthetic':'true'},{'synthetic':1},
    {'schema_version':'v0'},{'device_id':'demo-device-b'},{'patient_id':'p-injected'},
    {'sequence':True},{'sequence':-1},{'session_id':'not-uuid'},
    {'measured_at':'2026-11-14T12:00:00'},
    {'measured_at':(NOW-timedelta(seconds=121)).isoformat()},
    {'measured_at':(NOW+timedelta(seconds=31)).isoformat()},
    {'quality':'invalid'}, {'metrics':None}, {'calibration_version':'C-OTHER'},
    {'metrics':{'contact_seconds':60,'episodes':8,'thumb_pct':float('nan'),'palm_pct':30}},
])
def test_invalid_packets_do_not_change_freshness_or_store_report(bank,change):
    with pytest.raises(IngestionRejected): ingest(bank,TOPIC,packet(**change),now=NOW)
    with bank() as db:
        assert db.scalar(select(Report)) is None
        assert 'last_seen' not in db.get(DomainRecord,'demo-device-a').data


def test_qos_duplicate_and_out_of_order_rejected(bank):
    ident=str(uuid4())
    ingest(bank,TOPIC,packet(session_id=ident,sequence=2),now=NOW)
    for seq in (2,1):
        with pytest.raises(IngestionRejected,match='replay'): ingest(bank,TOPIC,packet(session_id=ident,sequence=seq),now=NOW)
    with bank() as db: assert len(list(db.scalars(select(Report))))==1


def test_new_session_does_not_allow_replay_of_previous_session(bank):
    ident=str(uuid4())
    ingest(bank,TOPIC,packet(session_id=ident),now=NOW)
    ingest(bank,TOPIC,packet(window_start=NOW.isoformat(),measured_at=(NOW+timedelta(seconds=60)).isoformat()),now=NOW+timedelta(seconds=60))
    with pytest.raises(IngestionRejected): ingest(bank,TOPIC,packet(session_id=ident),now=NOW)


@pytest.mark.parametrize('start',[NOW,NOW+timedelta(seconds=1),NOW-timedelta(seconds=3601),NOW-timedelta(seconds=59)])
def test_invalid_interval_or_contact_exceeding_duration_refused(bank,start):
    with pytest.raises(IngestionRejected,match='invalid_interval'):ingest(bank,TOPIC,packet(window_start=start.isoformat()),now=NOW)


def test_global_watermark_blocks_overlap_even_with_new_session(bank):
    ingest(bank,TOPIC,packet(),now=NOW)
    with pytest.raises(IngestionRejected,match='overlapping_interval'):
        ingest(bank,TOPIC,packet(sequence=999,window_start=(NOW-timedelta(seconds=30)).isoformat(),measured_at=(NOW+timedelta(seconds=30)).isoformat()),now=NOW+timedelta(seconds=30))
    with bank() as db:assert len(list(db.scalars(select(Report))))==1


@pytest.mark.parametrize('mode',['registry','domain','serial'])
def test_revoked_and_rotated_certificates_rejected(bank,mode):
    with bank.begin() as db:
        if mode=='registry': db.get(DeviceIdentity,'skm-001').revoked_at=1
        else:
            row=db.get(DomainRecord,'demo-device-a')
            row.data={**row.data,'certificate':{'revoked':mode=='domain','serial':'other' if mode=='serial' else '123'}}
    with pytest.raises(IngestionRejected): ingest(bank,TOPIC,packet(),now=NOW)


def test_transport_and_duplicated_json_keys(bank):
    for topic,data,retained in [(TOPIC,packet(),True),('skelivia/v1/devices/other/telemetry',packet(),False),(TOPIC,b'{"synthetic":true,"synthetic":false}',False),(TOPIC,b'x'*16385,False)]:
        with pytest.raises(IngestionRejected): ingest(bank,topic,data,retained=retained,now=NOW)


def test_invalid_quality_records_gap_without_fake_numbers(bank):
    report_id=ingest(bank,TOPIC,packet(quality='invalid',metrics=None),now=NOW)
    with bank() as db:
        report=db.get(Report,report_id)
        assert report.quality=='invalid' and 'contact_seconds' not in report.metrics


def usage(kind='high_force', origin='computed', at_seconds=4.95):
    return {'kind':kind,'origin':origin,'at_seconds':at_seconds}


def usage_settings(bank, **values):
    with bank.begin() as db:
        settings=db.get(DomainRecord,'usage-settings')
        if settings:settings.data=values
        else:db.add(DomainRecord(id='usage-settings',kind='settings',owner_id='u-alice',data=values,created_at=0,updated_at=0))


def test_usage_notifications_bound_to_owner_and_labels_are_synthetic(commands_bank):
    usage_settings(commands_bank,pause_enabled=True)
    run_id=str(uuid4())
    raw=packet(session_id=run_id,sequence=7,events=[usage(k,origin='manual') for k in ('pause_reminder','high_force','quiet_contact','absent')])
    report_id=ingest(commands_bank,TOPIC,raw,now=NOW)
    with commands_bank() as db:
        notices=list(db.scalars(select(DomainRecord).where(DomainRecord.kind=='notification')))
        assert len(notices)==4 and {n.owner_id for n in notices}=={'u-alice'}
        assert all(n.data['synthetic'] and n.data['title'].startswith('Simulation manuelle :') and n.data['origin']=='manual' for n in notices)
        assert all(n.data['simulation_run']==run_id and n.data['sequence']==7 for n in notices)
        assert sorted(n.data['kind'] for n in notices)==['pause','usage','usage','usage']
        result=db.get(Report,report_id).metrics['usage_events']
        assert all(e['status']=='notification_created' for e in result)
    with pytest.raises(IngestionRejected):ingest(commands_bank,TOPIC,raw,now=NOW)
    with commands_bank() as db:
        assert len(list(db.scalars(select(DomainRecord).where(DomainRecord.kind=='notification'))))==4


@pytest.mark.parametrize('events',[
    [usage(at_seconds=-1)], [usage(at_seconds=60.01)], [usage(at_seconds=float('nan'))],
    [usage(origin='physical')], [usage(kind='medical_risk')],
    [usage(),usage()], [usage()]*5, [{**usage(),'owner_id':'other'}],
    [{**usage(),'patient_id':'other'}], [{**usage(),'title':'Injected'}],
])
def test_usage_event_schema_rejects_forgery_and_invalid_offsets(commands_bank,events):
    with pytest.raises(IngestionRejected):ingest(commands_bank,TOPIC,packet(events=events),now=NOW)
    with commands_bank() as db:
        assert db.scalar(select(Report)) is None
        assert db.scalar(select(DomainRecord).where(DomainRecord.kind=='notification')) is None


@pytest.mark.parametrize('quality',['invalid','calibration_required'])
def test_usage_events_never_accepted_without_valid_measurements(commands_bank,quality):
    with pytest.raises(IngestionRejected,match='invalid_usage_events'):
        ingest(commands_bank,TOPIC,packet(events=[usage()],quality=quality,metrics=None),now=NOW)


@pytest.mark.parametrize('settings,expected',[
    ({},'pause_disabled'),
    ({'pause_enabled':False},'pause_disabled'),
    ({'pause_enabled':True,'snoozed_until':NOW.timestamp()+300},'pause_snoozed'),
])
def test_usage_pause_honors_disabled_and_snoozed_preferences(commands_bank,settings,expected):
    usage_settings(commands_bank,**settings)
    report_id=ingest(commands_bank,TOPIC,packet(events=[usage('pause_reminder')]),now=NOW)
    with commands_bank() as db:
        assert db.get(Report,report_id).metrics['usage_events'][0]['status']==expected
        assert db.scalar(select(DomainRecord).where(DomainRecord.kind=='notification')) is None


def test_usage_event_cooldown_is_per_kind_and_device_survives_new_sessions(commands_bank):
    ingest(commands_bank,TOPIC,packet(events=[usage()]),now=NOW)
    after=NOW+timedelta(seconds=30)
    report_id=ingest(commands_bank,TOPIC,packet(window_start=NOW.isoformat(),measured_at=after.isoformat(),metrics={'contact_seconds':30.,'episodes':4,'thumb_pct':80.,'palm_pct':80.},events=[usage(),usage('absent')]),now=after)
    with commands_bank() as db:
        assert [e['status'] for e in db.get(Report,report_id).metrics['usage_events']]==['cooldown','notification_created']
        assert len(list(db.scalars(select(DomainRecord).where(DomainRecord.kind=='notification'))))==2
    end=NOW+timedelta(seconds=60)
    report_id=ingest(commands_bank,TOPIC,packet(window_start=after.isoformat(),measured_at=end.isoformat(),metrics={'contact_seconds':30.,'episodes':4,'thumb_pct':80.,'palm_pct':80.},events=[usage()]),now=end)
    with commands_bank() as db:
        assert db.get(Report,report_id).metrics['usage_events'][0]['status']=='notification_created'
        assert db.get(DomainRecord,'demo-device-a').data['usage_notice_times']['high_force']==end.timestamp()


@pytest.mark.parametrize('change',['inactive','wrong_role','missing'])
def test_usage_event_cannot_notify_inactive_missing_or_nonpatient_owner(commands_bank,change):
    from app.models import Account
    with commands_bank.begin() as db:
        account=db.get(Account,'u-alice')
        if change=='inactive':account.active=False
        elif change=='wrong_role':account.role='support'
        else:db.delete(account)
    report_id=ingest(commands_bank,TOPIC,packet(events=[usage()]),now=NOW)
    with commands_bank() as db:
        assert db.get(Report,report_id).metrics['usage_events'][0]['status']=='owner_unavailable'
        assert db.scalar(select(DomainRecord).where(DomainRecord.kind=='notification')) is None


@pytest.fixture
def commands_bank(bank):
    from app.models import Account
    from app.domain_models import DomainJob
    with bank.begin() as db:
        db.add(Account(id='u-alice',username='alice-test',name='Synthetic',role='user',org_id='test',patient_id='p-alice',password_hash='not-a-password',otp_secret='unused',active=True))
        db.get(DomainRecord,'demo-device-a').org_id='test'
        db.add(DomainJob(id='job-cal',kind='calibration',target_id='demo-device-a',owner_id='u-alice',status='pending',payload={'device_id':'demo-device-a'},result={},created_at=1,updated_at=1))
    return bank


def acknowledgement(command,**changes):
    payload={'schema_version':'skelivia.ack.v1','synthetic':True,'job_id':command['job_id'],'device_id':command['device_id'],'kind':command['kind'],'nonce':command['nonce'],'status':'succeeded','proof_id':str(uuid4()),'measured_at':NOW.isoformat(),'calibration_version':'C-TEST-02'}
    payload.update(changes)
    return json.dumps(payload).encode()


def test_command_requires_bound_ack_and_never_claims_physical_calibration(commands_bank):
    from app.worker import pending_commands,accept_ack
    from app.domain_models import DomainJob
    commands=pending_commands(commands_bank,now=NOW.timestamp());assert len(commands)==1
    topic,raw=commands[0];command=json.loads(raw)
    assert topic=='skelivia/v1/devices/skm-001/commands'
    with commands_bank() as db:assert db.get(DomainJob,'job-cal').status=='sent'
    accept_ack(commands_bank,topic.replace('/commands','/ack'),acknowledgement(command),now=NOW.timestamp())
    with commands_bank() as db:
        job=db.get(DomainJob,'job-cal');device=db.get(DomainRecord,'demo-device-a')
        assert job.status=='completed' and job.result['synthetic'] is True
        assert device.data['calibration']=='C-TEST-02'
        assert device.data['calibration_status']=='synthetic_reference'
        assert db.scalar(select(DomainRecord).where(DomainRecord.kind=='notification')).owner_id=='u-alice'
    with pytest.raises(IngestionRejected):accept_ack(commands_bank,topic.replace('/commands','/ack'),acknowledgement(command),now=NOW.timestamp())


@pytest.mark.parametrize('changes',[{'synthetic':False},{'nonce':'a'*64},{'device_id':'demo-device-b'},{'job_id':'not-job'},{'proof_id':'fake'},{'calibration_version':None},{'measured_at':(NOW-timedelta(seconds=121)).isoformat()}])
def test_ack_forgery_stale_and_real_refused(commands_bank,changes):
    from app.worker import pending_commands,accept_ack
    command=json.loads(pending_commands(commands_bank,now=NOW.timestamp())[0][1])
    with pytest.raises(IngestionRejected):accept_ack(commands_bank,'skelivia/v1/devices/skm-001/ack',acknowledgement(command,**changes),now=NOW.timestamp())


def test_ack_rechecks_revocation_and_owner_active(commands_bank):
    from app.worker import pending_commands,accept_ack
    from app.models import Account
    command=json.loads(pending_commands(commands_bank,now=NOW.timestamp())[0][1])
    with commands_bank.begin() as db:db.get(Account,'u-alice').active=False
    with pytest.raises(IngestionRejected,match='owner_inactive'):accept_ack(commands_bank,'skelivia/v1/devices/skm-001/ack',acknowledgement(command),now=NOW.timestamp())


def test_sent_job_expires_without_fabricated_success(commands_bank):
    from app.worker import pending_commands
    from app.domain_models import DomainJob
    pending_commands(commands_bank,now=NOW.timestamp())
    assert pending_commands(commands_bank,now=NOW.timestamp()+121)==[]
    with commands_bank() as db:assert db.get(DomainJob,'job-cal').status=='expired'


def test_signed_synthetic_update_requires_approved_patch_and_matching_digest(commands_bank,tmp_path):
    import importlib.util
    from pathlib import Path
    from app.worker import pending_commands,accept_ack,verified_artifact
    from app.models import Account
    from app.domain_models import DomainJob,DomainDiagnostic,SupportScope
    spec=importlib.util.spec_from_file_location('prep',Path(__file__).resolve().parents[1]/'scripts/prepare_infra.py');prep=importlib.util.module_from_spec(spec);spec.loader.exec_module(prep)
    prep.synthetic_firmware(tmp_path)
    artifact_root=tmp_path/'firmware'
    with commands_bank.begin() as db:
        db.delete(db.get(DomainJob,'job-cal'))
        db.add(Account(id='support',username='support-test',name='Synthetic',role='support',org_id='test',password_hash='unused',otp_secret='unused',active=True))
        db.add(SupportScope(support_id='support',org_id='test',active=True))
        db.add(DomainRecord(id='ticket',kind='ticket',owner_id='u-alice',device_id='demo-device-a',assigned_to='support',status='in_progress',data={},created_at=0,updated_at=0))
        db.add(DomainDiagnostic(ticket_id='ticket',device_id='demo-device-a',support_id='support',owner_id='u-alice',expires=NOW.timestamp()+500,active=True))
        db.add(DomainRecord(id='patch-demo',kind='patch',status='approved',data={'version':'2.4.2'},created_at=0,updated_at=0))
        db.add(DomainJob(id='job-update',kind='update',target_id='demo-device-a',owner_id='u-alice',assigned_to='support',status='pending',payload={'ticket_id':'ticket','patch_id':'patch-demo','version':'2.4.2'},result={},created_at=0,updated_at=0))
    command=json.loads(pending_commands(commands_bank,now=NOW.timestamp(),artifact_root=artifact_root)[0][1])
    with pytest.raises(IngestionRejected,match='artifact_mismatch'):
        accept_ack(commands_bank,'skelivia/v1/devices/skm-001/ack',acknowledgement(command,firmware_version='2.4.2',artifact_sha256='0'*64),now=NOW.timestamp(),artifact_root=artifact_root)
    accept_ack(commands_bank,'skelivia/v1/devices/skm-001/ack',acknowledgement(command,firmware_version='2.4.2',artifact_sha256=command['artifact']['sha256']),now=NOW.timestamp(),artifact_root=artifact_root)
    with commands_bank() as db:
        assert db.get(DomainJob,'job-update').status=='completed'
        assert db.get(DomainRecord,'demo-device-a').data['calibration_status']=='required'
    (artifact_root/'synthetic-2.4.2.bin').write_bytes(b'tampered')
    with pytest.raises(IngestionRejected,match='digest'):verified_artifact('patch-demo','2.4.2',artifact_root)

