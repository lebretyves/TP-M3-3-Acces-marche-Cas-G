"""Deletion adapter tests: temporary database only, never the running bank."""
import time
import pytest
from sqlalchemy import select
from app.database import database
from app.seed import seed
from app.domain_seed import seed_domain
from app.models import Account, Report, WebSession
from app.domain_models import DomainRecord as R, DomainJob as J, DomainGrant as G, DomainDiagnostic as D
from app.push_models import PushSubscription, PushDelivery
from scripts.domain_operations import execute_deletion, OperationRefused


@pytest.fixture
def deletion_bank(tmp_path,monkeypatch):
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(tmp_path/'key'))
    engine,factory=database('sqlite:///'+(tmp_path/'deletion.db').as_posix());seed(factory)
    with factory() as db:
        seed_domain(db);now=time.time()
        db.add(R(id='delete-qa',kind='deletion',owner_id='u-alice',patient_id='p-alice',status='pending',data={'reason':'QA personal reason'},created_at=now,updated_at=now))
        db.add(J(id='delete-job',kind='deletion',target_id='delete-qa',owner_id='s-securite',status='pending',payload={'account_id':'u-alice','review_reason':'QA reviewed'},result={},created_at=now,updated_at=now))
        db.add(J(id='cert-job',kind='certificate',target_id='demo-device-a',owner_id='s-securite',status='pending',payload={'operation':'renew'},result={},created_at=now,updated_at=now))
        db.add(WebSession(token_hash='a'*64,user_id='u-alice',csrf='qa',expires=now+900,last_seen=now,authenticated_at=now))
        db.add(G(id='share-qa',owner_id='u-alice',patient_id='p-alice',clinician_id='c-lina',start='2026-01-01',end='2026-12-31',categories=['contact'],expires=now+900,active=True))
        db.add(D(ticket_id='ticket-alice',owner_id='u-alice',support_id='t-support',device_id='demo-device-a',expires=now+900,active=True))
        db.add(PushSubscription(id='push-qa',owner_id='u-alice',endpoint_hash='a'*64,label='QA',data={'endpoint':'sensitive'},active=True,created_at=now,updated_at=now))
        db.commit()
    yield factory
    engine.dispose()


def test_dry_run_no_mutation_and_explicit_clearance_required(deletion_bank):
    with deletion_bank() as db:
        plan=execute_deletion(db,'delete-job');assert plan['dry_run'] and plan['counts']['reports']==2
        db.commit()
    with deletion_bank() as db:
        assert db.get(Account,'u-alice') and db.get(J,'delete-job').status=='pending'
        with pytest.raises(OperationRefused):execute_deletion(db,'delete-job',execute=True)
        db.rollback()


def test_execute_scope_tombstone_revocations_and_idempotency(deletion_bank):
    with deletion_bank() as db:
        result=execute_deletion(db,'delete-job',execute=True,policy_reference='QA-POLICY-ONLY',retention_cleared=True,operator='qa-operator');db.commit()
        assert result['scope']=='application_database' and result['evidence_id']
    with deletion_bank() as db:
        assert db.get(Account,'u-alice') is None
        assert db.get(Account,'u-benoit') is not None
        assert not db.scalars(select(Report).where(Report.patient_id=='p-alice')).all()
        assert db.scalars(select(Report).where(Report.patient_id=='p-benoit')).all()
        assert db.get(WebSession,'a'*64) is None and db.get(G,'share-qa') is None
        assert not db.get(D,'ticket-alice').active and db.get(PushSubscription,'push-qa') is None
        device=db.get(R,'demo-device-a');assert device.status=='retired' and device.patient_id is None and device.owner_id is None
        assert db.get(J,'cert-job').status=='cancelled'
        tombstone=db.get(R,'delete-qa');assert tombstone.patient_id=='p-alice' and tombstone.status=='completed'
        assert 'QA personal reason' not in str(tombstone.data) and tombstone.data['proof']['policy_reference']=='QA-POLICY-ONLY'
        assert execute_deletion(db,'delete-job',execute=True,policy_reference='QA',retention_cleared=True)['already_completed']


def test_scope_mismatch_rolls_back_and_missing_review_refused(deletion_bank):
    with deletion_bank() as db:
        job=db.get(J,'delete-job');job.payload={'account_id':'u-benoit'};db.commit()
    with deletion_bank() as db:
        with pytest.raises(OperationRefused):execute_deletion(db,'delete-job',execute=True,policy_reference='QA',retention_cleared=True)
        db.rollback()
    with deletion_bank() as db:assert db.get(Account,'u-alice') and db.get(Account,'u-benoit')


def test_seed_does_not_resurrect_deleted_patient(deletion_bank):
    with deletion_bank() as db:
        execute_deletion(db,'delete-job',execute=True,policy_reference='QA-SEED',retention_cleared=True)
        db.commit()
    seed(deletion_bank)
    with deletion_bank() as db:
        seed_domain(db)
        db.commit()
    with deletion_bank() as db:
        assert db.get(Account,'u-alice') is None
        assert not db.scalars(select(Report).where(Report.patient_id=='p-alice')).all()
        assert not db.scalars(select(R).where(R.patient_id=='p-alice',R.kind.in_(['document','profile']))).all()
        assert db.get(R,'demo-device-a').status=='retired'
        assert db.get(R,'delete-qa').status=='completed'
        assert db.get(Account,'u-benoit') is not None
