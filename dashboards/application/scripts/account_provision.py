"""Offline, approved Keycloak provisioning. Creates disabled identities only.

No email or password is sent or generated for the recipient. Enrolment and activation
are explicit subsequent operator steps. All unit tests use an in-memory fake IdP.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from argon2 import PasswordHasher
import pyotp
import httpx
from app.database import register_models
from app.models import Account, OIDCIdentity
from app.domain_models import DomainRecord as R, DomainJob as J
from scripts.domain_operations import OperationRefused


class KeycloakOperator:
    def __init__(self,base_url,realm,token,*,allow_private_http=False,verify=True,transport=None):
        u=urlsplit(base_url)
        permitted_http=allow_private_http and u.scheme=='http' and u.hostname in {'keycloak','127.0.0.1','localhost'}
        if (u.scheme!='https' and not permitted_http) or u.username or u.password or u.query or u.fragment:raise OperationRefused('Explicit HTTPS IdP URL required (private Docker HTTP requires explicit operator override).')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',realm):raise OperationRefused('Invalid realm.')
        if not token or len(token)>16384 or any(c.isspace() for c in token):raise OperationRefused('Invalid operator bearer token.')
        self.client=httpx.Client(base_url=base_url.rstrip('/')+'/',headers={'Authorization':'Bearer '+token},timeout=10,follow_redirects=False,trust_env=False,verify=verify,transport=transport)
        self.path='admin/realms/'+realm+'/users'

    def close(self):self.client.close()

    def ensure_disabled_user(self,username,name,job_id):
        response=self.client.get(self.path,params={'username':username,'exact':'true'})
        if response.status_code!=200:raise OperationRefused('IdP lookup failed; no credential details published.')
        matches=response.json()
        if not isinstance(matches,list) or len(matches)>1:raise OperationRefused('Ambiguous IdP identity.')
        if not matches:
            response=self.client.post(self.path,json={'username':username,'firstName':name,'enabled':False,'requiredActions':['CONFIGURE_TOTP','UPDATE_PASSWORD'],'attributes':{'skelivia_job':[job_id]}})
            if response.status_code not in {201,409}:raise OperationRefused('IdP creation failed; retry remains safe.')
            response=self.client.get(self.path,params={'username':username,'exact':'true'})
            if response.status_code!=200:raise OperationRefused('IdP verification failed; created identity remains disabled.')
            matches=response.json()
        if not isinstance(matches,list) or len(matches)!=1:raise OperationRefused('Unable to verify IdP identity.')
        user=matches[0]
        if user.get('attributes',{}).get('skelivia_job')!=[job_id] or user.get('enabled') is not False:raise OperationRefused('Existing or enabled identity cannot be adopted by this job.')
        if not {'CONFIGURE_TOTP','UPDATE_PASSWORD'}<=set(user.get('requiredActions',[])):raise OperationRefused('Enrolment requirements are missing.')
        subject=user.get('id','')
        if not re.fullmatch(r'[A-Za-z0-9-]{1,80}',subject):raise OperationRefused('Invalid IdP subject.')
        return subject


def provisioning_plan(db,job_id):
    job=db.scalar(select(J).where(J.id==job_id).with_for_update())
    if not job or job.kind!='account_provision':raise OperationRefused('Approved provisioning job required.')
    request=db.get(R,job.target_id)
    if not request or request.kind!='account_request' or request.data.get('operation')!='create':raise OperationRefused('Approved creation request required.')
    if job.status=='provisioned_inactive' and request.status=='provisioned_inactive':return job,request,True
    if job.status!='pending' or request.status!='approved_pending_provision':raise OperationRefused('Creation request must be approved and pending provisioning.')
    requester_id=request.owner_id;approver_id=request.data.get('approver_id')
    if not approver_id or requester_id==approver_id or job.payload.get('requester_id')!=requester_id or job.payload.get('approver_id')!=approver_id:raise OperationRefused('Distinct approved identities required.')
    for identity in [requester_id,approver_id]:
        account=db.get(Account,identity)
        if not account or not account.active or account.role!='security':raise OperationRefused('Approvals are no longer valid.')
    for key in ['username','name','role','org_id']:
        if not request.data.get(key) or request.data[key]!=job.payload.get(key):raise OperationRefused('Approved payload mismatch.')
    return job,request,False


def provision_account(db,job_id,*,execute=False,policy_reference=None,client=None):
    job,request,completed=provisioning_plan(db,job_id)
    result={'operation':'account_provision','dry_run':not execute,'already_provisioned':completed,'active':False,'enrolment_required':True}
    if completed or not execute:return result
    if not policy_reference or not 1<=len(policy_reference)<=160 or any(ord(c)<32 for c in policy_reference):raise OperationRefused('Bounded operator policy reference required.')
    if client is None:raise OperationRefused('Explicit operator IdP client required.')
    p=request.data
    existing=db.scalar(select(Account).where(Account.username==p['username']))
    if existing:raise OperationRefused('Username already exists in the application.')
    subject=client.ensure_disabled_user(p['username'],p['name'],job.id)
    if db.get(OIDCIdentity,subject):raise OperationRefused('IdP subject already mapped.')
    suffix=hashlib.sha256(job.id.encode()).hexdigest()[:24];account_id='acct-'+suffix
    # This random local secret is intentionally discarded: no known local credentials.
    account=Account(id=account_id,username=p['username'],name=p['name'],role=p['role'],org_id=p['org_id'],patient_id='patient-'+suffix if p['role']=='user' else None,active=False,password_hash=PasswordHasher().hash(secrets.token_urlsafe(48)),otp_secret=pyotp.random_base32())
    db.add(account);db.flush();db.add(OIDCIdentity(subject=subject,user_id=account_id))
    now=time.time();proof={'account_id':account_id,'idp_identity_verified':True,'idp_enabled':False,'application_active':False,'enrolment_required':['Configure strong MFA through the approved IAM procedure','Verify the identity enrolment','Enable IdP account explicitly','Request and approve application reactivation separately'],'policy_reference':policy_reference,'at':now}
    request.status='provisioned_inactive';request.updated_at=now;request.data={**request.data,'provisioning':proof}
    job.status='provisioned_inactive';job.updated_at=now;job.result={'status':'provisioned_inactive','evidence_id':'provision-'+suffix,'verified_at':now,'detail':'Identité et correspondance créées désactivées. Enrôlement MFA et activation distincts requis.'}
    db.flush();return {**result,'account_id':account_id,'status':'provisioned_inactive'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--job',required=True)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--execute',action='store_true')
    parser.add_argument('--policy-reference');args=parser.parse_args()
    filename=os.getenv('SKELIVIA_OPERATOR_DATABASE_URL_FILE')
    if not filename:raise SystemExit('Explicit operator database URL file required.')
    register_models();engine=create_engine(Path(filename).read_text().strip(),hide_parameters=True)
    if engine.dialect.name!='postgresql':raise SystemExit('Operator CLI requires PostgreSQL.')
    factory=sessionmaker(engine,expire_on_commit=False);client=None
    try:
        with factory() as db:
            if db.execute(text('SELECT current_user')).scalar()!='skelivia_owner':raise OperationRefused('Dedicated operator database identity required.')
            provisioning_plan(db,args.job)
            if args.execute:
                tokenfile=os.getenv('SKELIVIA_OPERATOR_KEYCLOAK_TOKEN_FILE')
                if not tokenfile:raise OperationRefused('Short-lived IAM operator token file required.')
                client=KeycloakOperator(os.environ['SKELIVIA_OPERATOR_KEYCLOAK_URL'],os.environ.get('SKELIVIA_OPERATOR_KEYCLOAK_REALM','skelivia'),Path(tokenfile).read_text().strip(),allow_private_http=os.getenv('SKELIVIA_OPERATOR_ALLOW_PRIVATE_HTTP')=='true',verify=os.getenv('SKELIVIA_OPERATOR_CA_FILE') or True)
            result=provision_account(db,args.job,execute=args.execute,policy_reference=args.policy_reference,client=client)
            if args.execute:db.commit()
            else:db.rollback()
            print(json.dumps(result,ensure_ascii=False,indent=2))
    except OperationRefused as exc:raise SystemExit(str(exc)) from None
    except Exception:raise SystemExit('Provisioning failed. Retry uses the job marker; any created IdP identity remains disabled. No credentials printed.') from None
    finally:
        if client:client.close()
        engine.dispose()


if __name__=='__main__':main()
