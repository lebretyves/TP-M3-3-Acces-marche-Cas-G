"""Privileged offline deletion adapter. Dry-run by default; no HTTP entry point.

Example: python -m scripts.domain_operations --job JOB_ID --dry-run
Execution additionally requires --execute --retention-cleared --policy-reference REF.
Only SKELIVIA_OPERATOR_DATABASE_URL_FILE is accepted, never application credentials.
"""
import argparse
import json
import os
from pathlib import Path
import time
import uuid
from sqlalchemy import create_engine, delete, select, or_, text
from sqlalchemy.orm import sessionmaker
from app.database import register_models
from app.models import Account, Alert, CareLink, LoginDevice, OIDCIdentity, OIDCState, Report, Share, Ticket, WebSession
from app.domain_models import DomainRecord as R, DomainJob as J, DomainGrant as G, DomainDiagnostic as D
from app.push_models import PushSubscription, PushDelivery, PushSchedule
from app.transport_models import DeviceIdentity, IngestCursor, IngestDeviceCursor, IngestReceipt


class OperationRefused(ValueError):
    pass


def deletion_plan(db,job_id):
    job=db.scalar(select(J).where(J.id==job_id).with_for_update())
    if not job or job.kind!='deletion':raise OperationRefused('Validated deletion job required.')
    request=db.get(R,job.target_id)
    if not request or request.kind!='deletion' or not request.patient_id:raise OperationRefused('Deletion request and patient tombstone reference required.')
    if job.status=='completed' and request.status=='completed':return {'already_completed':True,'job':job,'request':request,'counts':{}}
    if job.status!='pending' or request.status!='pending':raise OperationRefused('Job must be reviewed and pending.')
    reviewer=db.get(Account,job.owner_id)
    if not reviewer or not reviewer.active or reviewer.role!='security':raise OperationRefused('Active security reviewer required.')
    owner=db.get(Account,request.owner_id)
    if not owner or owner.role!='user' or owner.patient_id!=request.patient_id or job.payload.get('account_id')!=owner.id:raise OperationRefused('Job/request/account scope mismatch.')
    devices=list(db.scalars(select(R).where(R.kind=='device',R.owner_id==owner.id)))
    reports=list(db.scalars(select(Report.id).where(Report.patient_id==request.patient_id)))
    records=list(db.scalars(select(R).where(or_(R.owner_id==owner.id,R.patient_id==request.patient_id),R.id!=request.id,R.kind.notin_(['audit','device','deletion']))))
    counts={'reports':len(reports),'domain_records':len(records),'devices_to_retire':len(devices),'sessions':len(db.scalars(select(WebSession.token_hash).where(WebSession.user_id==owner.id)).all()),'subscriptions':len(db.scalars(select(PushSubscription.id).where(PushSubscription.owner_id==owner.id)).all())}
    return {'already_completed':False,'job':job,'request':request,'owner':owner,'devices':devices,'reports':reports,'records':records,'counts':counts}


def execute_deletion(db,job_id,*,execute=False,policy_reference=None,retention_cleared=False,operator='offline-operator'):
    plan=deletion_plan(db,job_id)
    safe={'operation':'deletion','dry_run':not execute,'already_completed':plan['already_completed'],'counts':plan['counts'],'scope':'application_database'}
    if plan['already_completed'] or not execute:return safe
    if not retention_cleared or not policy_reference or not 1<=len(policy_reference)<=160 or any(ord(c)<32 for c in policy_reference):raise OperationRefused('Explicit retention clearance and bounded policy reference required.')
    now=time.time();job=plan['job'];request=plan['request'];owner=plan['owner'];owner_id=owner.id;patient=request.patient_id
    sessions=list(db.scalars(select(WebSession.token_hash).where(WebSession.user_id==owner_id)))
    db.execute(delete(OIDCState).where(OIDCState.session_hash.in_(sessions)))
    db.execute(delete(WebSession).where(WebSession.user_id==owner_id))
    db.execute(delete(LoginDevice).where(LoginDevice.user_id==owner_id))
    db.execute(delete(OIDCIdentity).where(OIDCIdentity.user_id==owner_id))
    for diagnostic in db.scalars(select(D).where(D.owner_id==owner_id)):diagnostic.active=False
    db.execute(delete(PushDelivery).where(PushDelivery.owner_id==owner_id))
    db.execute(delete(PushSubscription).where(PushSubscription.owner_id==owner_id))
    db.execute(delete(PushSchedule).where(PushSchedule.owner_id==owner_id))
    db.execute(delete(G).where(or_(G.owner_id==owner_id,G.patient_id==patient)))
    db.execute(delete(Share).where(Share.report_id.in_(plan['reports'])))
    db.execute(delete(CareLink).where(CareLink.patient_id==patient))
    db.execute(delete(Alert).where(Alert.patient_id==patient))
    db.execute(delete(Ticket).where(Ticket.user_id==owner_id))
    device_ids=[d.id for d in plan['devices']]
    for identity in db.scalars(select(DeviceIdentity).where(DeviceIdentity.device_id.in_(device_ids))):identity.revoked_at=now
    db.execute(delete(IngestReceipt).where(IngestReceipt.report_id.in_(plan['reports'])))
    db.execute(delete(IngestCursor).where(IngestCursor.device_id.in_(device_ids)))
    db.execute(delete(IngestDeviceCursor).where(IngestDeviceCursor.device_id.in_(device_ids)))
    db.execute(delete(Report).where(Report.patient_id==patient))
    for record in plan['records']:db.delete(record)
    for device in plan['devices']:
        cert=device.data.get('certificate',{})
        device.owner_id=None;device.patient_id=None;device.org_id=None;device.status='retired';device.updated_at=now
        device.data={'connection':'retired','calibration_status':'unavailable','history':[],'certificate':{'serial':cert.get('serial'),'expires':cert.get('expires'),'revoked':True,'revocation_scope':'application_ingestion'}}
    retired_targets=device_ids+[r.id for r in plan['records'] if r.kind=='ticket']
    for pending in db.scalars(select(J).where(or_(J.owner_id==owner_id,J.target_id.in_(retired_targets)),J.id!=job.id)):
        pending.status='cancelled';pending.payload={};pending.result={'status':'cancelled','detail':'Compte retiré du service.'};pending.updated_at=now
    # Account-change requests can contain names/usernames. Preserve workflow metadata only.
    for change in db.scalars(select(R).where(R.kind=='account_request')):
        if change.data.get('target_id')==owner_id:
            change.data={'target_id':owner_id,'operation':change.data.get('operation'),'redacted_after_deletion':True};change.updated_at=now
    db.delete(owner)
    evidence='deletion-proof-'+uuid.uuid4().hex
    proof={'id':evidence,'executed_at':now,'operator':operator,'policy_reference':policy_reference,'retention_cleared':True,'scope':'application_database','counts':plan['counts'],'external_obligations':['IdP account lifecycle','Broker certificate/CRL lifecycle','Backup expiry under approved retention policy','Previously downloaded copies cannot be recalled']}
    request.status='completed';request.updated_at=now
    request.data={'proof':proof,'history':[{'status':'completed','at':now}]}
    # This minimal tombstone is intentionally retained for restore reconciliation.
    request.patient_id=patient;request.owner_id=owner_id
    job.status='completed';job.updated_at=now;job.payload={'deletion_request_id':request.id}
    job.result={'status':'completed_database','evidence_id':evidence,'verified_at':now,'detail':'Suppression de la base applicative exécutée ; obligations externes consignées dans la preuve.'}
    db.flush()
    if db.get(Account,owner_id) or db.scalar(select(Report.id).where(Report.patient_id==patient)) or db.scalar(select(WebSession.token_hash).where(WebSession.user_id==owner_id)):
        raise OperationRefused('Post-deletion verification failed; transaction must roll back.')
    return {**safe,'evidence_id':evidence,'external_obligations':proof['external_obligations']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',required=True)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--dry-run',action='store_true');mode.add_argument('--execute',action='store_true')
    parser.add_argument('--retention-cleared',action='store_true');parser.add_argument('--policy-reference')
    args=parser.parse_args()
    filename=os.getenv('SKELIVIA_OPERATOR_DATABASE_URL_FILE')
    if not filename:raise SystemExit('Explicit operator database URL file required; application credentials are not accepted.')
    if args.execute and (not args.retention_cleared or not args.policy_reference):raise SystemExit('Execution requires retention clearance and policy reference.')
    register_models();engine=create_engine(Path(filename).read_text().strip(),hide_parameters=True)
    if engine.dialect.name!='postgresql':raise SystemExit('Operator CLI requires PostgreSQL; unit tests use isolated temporary databases directly.')
    factory=sessionmaker(engine,expire_on_commit=False)
    try:
        with factory() as db:
            identity=db.execute(text('SELECT current_user')).scalar()
            if identity!='skelivia_owner':raise OperationRefused('Dedicated migration/operator identity required.')
            result=execute_deletion(db,args.job,execute=args.execute,policy_reference=args.policy_reference,retention_cleared=args.retention_cleared,operator=identity)
            if args.execute:db.commit()
            else:db.rollback()
            print(json.dumps(result,ensure_ascii=False,indent=2))
    except OperationRefused as exc:raise SystemExit(str(exc)) from None
    except Exception:raise SystemExit('Operation failed; transaction rolled back. Inspect restricted operator logs without publishing credentials.') from None
    finally:engine.dispose()


if __name__=='__main__':main()
