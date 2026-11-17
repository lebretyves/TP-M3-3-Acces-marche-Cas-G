"""Account provisioning adapter uses a fake IdP and temporary DB only."""
import time
import pytest
from sqlalchemy import select
from app.database import database
from app.seed import seed
from app.models import Account, OIDCIdentity
from app.domain_models import DomainRecord as R, DomainJob as J
from scripts.account_provision import provision_account
from scripts.domain_operations import OperationRefused


class FakeIAM:
    def __init__(self):self.calls=[]
    def ensure_disabled_user(self,username,name,job_id):self.calls.append(job_id);return 'qa-subject-1'


@pytest.fixture
def provisioning_bank(tmp_path,monkeypatch):
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(tmp_path/'key'))
    engine,factory=database('sqlite:///'+(tmp_path/'provision.db').as_posix());seed(factory)
    with factory() as db:
        if not db.get(Account,'s-approbateur'):
            root=db.get(Account,'s-securite');db.add(Account(id='s-approbateur',username='qa.approver',name='QA approver',role='security',org_id='internal',active=True,password_hash=root.password_hash,otp_secret=root.otp_secret))
        now=time.time();payload={'operation':'create','username':'qa.new','name':'QA new account','role':'user','org_id':'qa-org','reason':'QA','approver_id':'s-approbateur'}
        db.add(R(id='request-qa',kind='account_request',owner_id='s-securite',status='approved_pending_provision',data=payload,created_at=now,updated_at=now))
        db.add(J(id='provision-qa',kind='account_provision',owner_id='s-approbateur',target_id='request-qa',status='pending',payload={**payload,'requester_id':'s-securite'},result={},created_at=now,updated_at=now));db.commit()
    yield factory
    engine.dispose()


def test_dry_run_does_not_contact_idp(provisioning_bank):
    iam=FakeIAM()
    with provisioning_bank() as db:
        assert provision_account(db,'provision-qa',client=iam)['dry_run'];db.commit()
        assert db.scalar(select(Account).where(Account.username=='qa.new')) is None
    assert not iam.calls


def test_provision_disabled_mapping_no_implicit_care_rights(provisioning_bank):
    iam=FakeIAM()
    with provisioning_bank() as db:
        result=provision_account(db,'provision-qa',execute=True,policy_reference='QA-ONBOARDING',client=iam);db.commit()
        account=db.get(Account,result['account_id'])
        assert account is not None and account.active is False
        assert db.get(OIDCIdentity,'qa-subject-1').user_id==account.id
        assert db.get(J,'provision-qa').status=='provisioned_inactive'
    with provisioning_bank() as db:assert provision_account(db,'provision-qa',execute=True,policy_reference='QA',client=iam)['already_provisioned']
    assert len(iam.calls)==1


def test_invalidated_approver_prevents_idp_request(provisioning_bank):
    iam=FakeIAM()
    with provisioning_bank() as db:db.get(Account,'s-approbateur').active=False;db.commit()
    with provisioning_bank() as db:
        with pytest.raises(OperationRefused):provision_account(db,'provision-qa',execute=True,policy_reference='QA',client=iam)
    assert not iam.calls
