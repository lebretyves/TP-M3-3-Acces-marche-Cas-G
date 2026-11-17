"""Certificate workflow proofs use an isolated database; no live device is revoked."""
import base64
import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base,Account
from app.domain_models import DomainRecord,DomainJob
from app.transport_models import DeviceIdentity

spec=importlib.util.spec_from_file_location('certificate_adapter',Path(__file__).resolve().parents[1]/'scripts/backup_restore.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)


@pytest.fixture
def bank(tmp_path,monkeypatch):
    key=tmp_path/'key';key.write_bytes(base64.b64encode(b'c'*32));monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(key))
    engine=create_engine('sqlite:///'+str(tmp_path/'cert.db'));Base.metadata.create_all(engine);sessions=sessionmaker(engine,expire_on_commit=False)
    with sessions.begin() as db:
        db.add(Account(id='security',username='security',name='Synthetic',role='security',org_id='test',password_hash='unused',otp_secret='unused',active=True))
        db.add(DomainRecord(id='device',kind='device',status='active',data={'certificate':{'serial':'123','revoked':False}},created_at=0,updated_at=0))
        db.add(DeviceIdentity(cert_cn='test-device',device_id='device',cert_serial='123'))
        db.add(DomainJob(id='job',kind='certificate',target_id='device',owner_id='security',status='pending',payload={'device_id':'device','operation':'revoke'},result={},created_at=0,updated_at=0))
    yield sessions
    engine.dispose()


def test_plan_read_only_and_stage_does_not_claim_completed(bank):
    plan=adapter.certificate_operation(bank,{'job_id':'job'})
    assert plan['dry_run'] and plan['status']=='pending'
    with bank() as db:assert db.get(DeviceIdentity,'test-device').revoked_at is None
    adapter.certificate_operation(bank,{'job_id':'job','phase':'stage','cert_serial':'123'})
    with bank() as db:
        assert db.get(DeviceIdentity,'test-device').revoked_at is not None
        assert db.get(DomainJob,'job').status=='revocation_pending_disconnect'
    with pytest.raises(ValueError):adapter.certificate_operation(bank,{'job_id':'job','phase':'complete','cert_serial':'123'})


def test_complete_requires_prior_stage_and_tls_proof(bank):
    proof={'job_id':'job','phase':'complete','cert_serial':'123','tls_rejection_verified':True,'crl_sha256':'a'*64}
    with pytest.raises(ValueError):adapter.certificate_operation(bank,proof)
    adapter.certificate_operation(bank,{'job_id':'job','phase':'stage','cert_serial':'123'})
    result=adapter.certificate_operation(bank,proof)
    assert result['status']=='completed'
    with bank() as db:assert db.get(DomainRecord,'device').data['certificate']['revocation_scope']=='application_and_broker_tls'
    assert adapter.certificate_operation(bank,proof)['already_completed']


@pytest.mark.parametrize('condition',['nonsecurity','serial','renew'])
def test_wrong_scope_and_renewal_are_not_executed(bank,condition):
    with bank.begin() as db:
        if condition=='nonsecurity':db.get(Account,'security').role='support'
        elif condition=='renew':db.get(DomainJob,'job').payload={'device_id':'device','operation':'renew'}
    with pytest.raises(ValueError):adapter.certificate_operation(bank,{'job_id':'job','phase':'stage','cert_serial':'changed' if condition=='serial' else '123'})
    with bank() as db:assert db.get(DeviceIdentity,'test-device').revoked_at is None
