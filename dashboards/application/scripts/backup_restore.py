"""Authenticated backups; restore only into a new, non-routed database.

The source must remain available to collect the current revocation/tombstone state.
No offline restore is offered without an independently maintained revocation ledger.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
from hashlib import sha256
import subprocess
import sys
import time
from uuid import uuid4
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
MAGIC = b'SKELIVIA-BACKUP-V1\x00'
RESTORE_NAME = re.compile(r'^skelivia_restore_[a-f0-9]{32}$')


def seal(data, key):
    nonce = secrets.token_bytes(12)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, MAGIC)


def unseal(data, key):
    if not data.startswith(MAGIC) or len(data) < len(MAGIC)+28:
        raise ValueError('Invalid backup format')
    body = data[len(MAGIC):]
    return AESGCM(key).decrypt(body[:12], body[12:], MAGIC)


def compose(*args, data=None):
    result = subprocess.run(['docker', 'compose', '-f', str(ROOT/'infra/compose.yaml'), *args], input=data, capture_output=True)
    if result.returncode:
        # Container errors may contain credentials or data: never forward raw output.
        raise RuntimeError('Isolated backup operation failed; inspect locally with authorized operator.')
    return result.stdout


def key_bytes():
    value = base64.b64decode((ROOT/'.runtime/infra/secrets/backup_key').read_bytes(), validate=True)
    if len(value) != 32:
        raise ValueError('Invalid backup key')
    return value


def record_operation(kind,details):
    payload={'kind':kind,'at':datetime.now(timezone.utc).isoformat(),**details}
    compose('run','--rm','--no-deps','-T','migrate','python','scripts/backup_restore.py','proof',data=json.dumps(payload).encode())


def backup():
    started=time.monotonic()
    raw = compose('exec', '-T', 'db', 'pg_dump', '-U', 'postgres', '-d', 'skelivia', '-Fc', '--no-owner', '--no-acl')
    folder = ROOT/'.runtime/backups'
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex+'.skb')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd,'wb') as handle:
        handle.write(seal(raw,key_bytes()))
    record_operation('backup',{'archive':path.name,'sha256':sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'encrypted':True,'duration_seconds':round(time.monotonic()-started,3)})
    print(json.dumps({'status':'encrypted_backup_created','file':str(path),'bytes':path.stat().st_size}))
    return path


def restore(path):
    started=time.monotonic()
    path = path.resolve()
    if not path.is_relative_to((ROOT/'.runtime/backups').resolve()):
        raise ValueError('Only local SKELIVIA backup files are accepted')
    raw = unseal(path.read_bytes(),key_bytes())  # Authenticate BEFORE database mutation.
    # Required current state, not the stale state inside the backup.
    policy = compose('run','--rm','--no-deps','-T','migrate','python','scripts/backup_restore.py','policy')
    parsed = json.loads(policy)
    if parsed.get('version') != 1:
        raise ValueError('Invalid restoration policy')
    name = 'skelivia_restore_'+uuid4().hex
    assert RESTORE_NAME.fullmatch(name)
    sql = f'CREATE DATABASE {name} OWNER skelivia_owner; REVOKE ALL ON DATABASE {name} FROM PUBLIC;'
    compose('exec','-T','db','psql','-X','-U','postgres','-d','postgres','-v','ON_ERROR_STOP=1',data=sql.encode())
    try:
        compose('exec','-T','db','pg_restore','-U','postgres','-d',name,'--role=skelivia_owner','--no-owner','--no-acl','--exit-on-error',data=raw)
        compose('run','--rm','--no-deps','-T','-e','SKELIVIA_RESTORE_DATABASE='+name,'migrate','python','scripts/backup_restore.py','reconcile',data=policy)
    except Exception:
        # No DROP and no production cutover. Leave failed restore inaccessible for review.
        print(json.dumps({'status':'isolated_restore_quarantined','database':name}))
        raise
    print(json.dumps({'status':'isolated_restore_reconciled','database':name,'routed':False,'sessions_and_grants':'revoked'}))
    record_operation('restore',{'database':name,'routed':False,'revocations_reapplied':True,'archive_sha256':sha256(path.read_bytes()).hexdigest(),'duration_seconds':round(time.monotonic()-started,3)})
    return name


def db_factory(target=None):
    sys.path.insert(0,str(ROOT))
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import sessionmaker
    url = make_url(Path(os.environ['SKELIVIA_DATABASE_URL_FILE']).read_text().strip())
    if target:
        if not RESTORE_NAME.fullmatch(target):
            raise ValueError('Unsafe restoration target')
        url = url.set(database=target)
    return sessionmaker(create_engine(url,hide_parameters=True),expire_on_commit=False)


def current_policy(sessions):
    from sqlalchemy import select
    from app.models import Account
    from app.domain_models import DomainRecord
    from app.transport_models import DeviceIdentity
    with sessions() as db:
        deleted = set(); subjects=[]
        for row in db.scalars(select(DomainRecord).where(DomainRecord.kind=='deletion',DomainRecord.status.in_(['completed','executed','deleted']))):
            patient = row.patient_id or row.data.get('patient_id')
            account = db.get(Account,row.owner_id) if row.owner_id else None
            patient = patient or (account.patient_id if account else None)
            if not patient:
                raise ValueError('Completed deletion lacks durable patient tombstone')
            deleted.add(patient)
            subjects.append({'patient_id':patient,'account_id':row.owner_id,'request_id':row.id,'proof_reference':row.data.get('proof',{}).get('id')})
        return {'version':1,'created_at':datetime.now(timezone.utc).isoformat(), 'deleted_patients':sorted(deleted),
                'deleted_subjects':subjects,
                'disabled_accounts':[r.id for r in db.scalars(select(Account).where(Account.active.is_(False)))],
                'revoked_devices':[r.cert_cn for r in db.scalars(select(DeviceIdentity).where(DeviceIdentity.revoked_at.is_not(None)))]}


def reconcile(sessions, policy):
    from sqlalchemy import delete, select, update, inspect, or_
    from app.models import Account, Alert, Report, Share, WebSession, CareLink, Ticket, OIDCState, OIDCIdentity, LoginDevice
    from app.domain_models import DomainRecord, DomainJob, DomainGrant, DomainDiagnostic
    from app.transport_models import DeviceIdentity, IngestCursor, IngestDeviceCursor, IngestReceipt
    from app.push_models import PushSubscription, PushDelivery, PushSchedule
    if policy.get('version') != 1:
        raise ValueError('Invalid current policy')
    with sessions.begin() as db:
        db.execute(delete(WebSession))
        db.execute(delete(OIDCState))
        db.execute(update(Share).values(active=False))
        db.execute(update(DomainGrant).values(active=False))
        db.execute(update(DomainDiagnostic).values(active=False))
        if inspect(db.bind).has_table('push_subscriptions'):
            db.execute(update(PushSubscription).values(active=False))
            db.execute(update(PushDelivery).where(PushDelivery.status.in_(['pending','retry'])).values(status='revoked'))
        for row in db.scalars(select(DomainRecord).where(DomainRecord.kind=='ticket')):
            row.data={**row.data,'diagnostic_revoked':True,'diagnostic_expires':0}
        for account_id in policy['disabled_accounts']:
            db.execute(update(Account).where(Account.id==account_id).values(active=False))
        for cn in policy['revoked_devices']:
            db.execute(update(DeviceIdentity).where(DeviceIdentity.cert_cn==cn).values(revoked_at=datetime.now(timezone.utc).timestamp()))
        for patient in policy['deleted_patients']:
            tombstones=[row for row in policy.get('deleted_subjects',[]) if row['patient_id']==patient]
            owners=set(db.scalars(select(Account.id).where(Account.patient_id==patient)))
            owners.update(row['account_id'] for row in tombstones if row.get('account_id'))
            ids=list(db.scalars(select(Report.id).where(Report.patient_id==patient)))
            db.execute(delete(Share).where(Share.report_id.in_(ids)))
            device_rows=list(db.scalars(select(DomainRecord).where(DomainRecord.kind=='device',or_(DomainRecord.patient_id==patient,DomainRecord.owner_id.in_(owners)))))
            devices=[row.id for row in device_rows]
            ticket_ids=list(db.scalars(select(DomainRecord.id).where(DomainRecord.kind=='ticket',DomainRecord.owner_id.in_(owners))))
            db.execute(delete(IngestReceipt).where(IngestReceipt.device_id.in_(devices)))
            db.execute(delete(IngestCursor).where(IngestCursor.device_id.in_(devices)))
            if inspect(db.bind).has_table('transport_device_cursor'):
                db.execute(delete(IngestDeviceCursor).where(IngestDeviceCursor.device_id.in_(devices)))
            db.execute(update(DeviceIdentity).where(DeviceIdentity.device_id.in_(devices)).values(revoked_at=datetime.now(timezone.utc).timestamp()))
            db.execute(delete(Report).where(Report.patient_id==patient))
            db.execute(delete(Alert).where(Alert.patient_id==patient))
            db.execute(delete(DomainGrant).where(DomainGrant.patient_id==patient))
            db.execute(delete(CareLink).where(CareLink.patient_id==patient))
            db.execute(delete(Ticket).where(Ticket.user_id.in_(owners)))
            db.execute(delete(LoginDevice).where(LoginDevice.user_id.in_(owners)))
            db.execute(delete(OIDCIdentity).where(OIDCIdentity.user_id.in_(owners)))
            if inspect(db.bind).has_table('push_subscriptions'):
                db.execute(delete(PushDelivery).where(PushDelivery.owner_id.in_(owners)))
                db.execute(delete(PushSubscription).where(PushSubscription.owner_id.in_(owners)))
                db.execute(delete(PushSchedule).where(PushSchedule.owner_id.in_(owners)))
            db.execute(delete(DomainRecord).where(or_(DomainRecord.patient_id==patient,DomainRecord.owner_id.in_(owners)),DomainRecord.kind.notin_(['deletion','audit','device'])))
            for device in device_rows:
                certificate=device.data.get('certificate',{})
                device.owner_id=None;device.patient_id=None;device.org_id=None;device.status='retired'
                device.data={'connection':'retired','calibration_status':'unavailable','history':[],'certificate':{'serial':certificate.get('serial'),'revoked':True,'revocation_scope':'application_ingestion'}}
            for job in db.scalars(select(DomainJob).where(or_(DomainJob.owner_id.in_(owners),DomainJob.target_id.in_(devices+ticket_ids)))):
                job.status='cancelled';job.payload={};job.result={'status':'cancelled','detail':'Compte retiré avant restauration.'}
            for request in db.scalars(select(DomainRecord).where(DomainRecord.kind=='account_request')):
                if request.data.get('target_id') in owners:
                    request.data={'target_id':request.data['target_id'],'redacted_after_deletion':True}
            db.execute(delete(Account).where(Account.id.in_(owners)))
            for tombstone in tombstones:
                marker=db.get(DomainRecord,tombstone['request_id'])
                if marker is None:
                    marker=DomainRecord(id=tombstone['request_id'],kind='deletion',created_at=datetime.now(timezone.utc).timestamp(),updated_at=datetime.now(timezone.utc).timestamp(),data={});db.add(marker)
                marker.owner_id=tombstone.get('account_id');marker.patient_id=patient;marker.status='completed'
                marker.data={'proof':{'id':tombstone.get('proof_reference'),'scope':'application_database','reapplied_after_restore':True}}
        # Restored jobs must never run obsolete commands automatically.
        db.execute(update(DomainJob).where(DomainJob.status.in_(['pending','queued','dispatched','sent'])).values(status='quarantined'))


def operation_proof(sessions, details):
    from app.domain_models import DomainRecord
    kind=details.get('kind')
    allowed={'backup':{'kind','at','archive','sha256','bytes','encrypted','duration_seconds'},'restore':{'kind','at','database','routed','revocations_reapplied','archive_sha256','duration_seconds'}}
    if kind not in allowed or set(details)!=allowed[kind]:raise ValueError('Invalid operation evidence')
    if kind=='restore' and (not RESTORE_NAME.fullmatch(details['database']) or details['routed'] is not False):raise ValueError('Invalid isolated restore evidence')
    now=datetime.now(timezone.utc).timestamp()
    with sessions.begin() as db:
        row=db.get(DomainRecord,'backup-state')
        if row is None:
            row=DomainRecord(id='backup-state',kind='proof',status='verified_local',data={},created_at=now,updated_at=now);db.add(row)
        row.data={**row.data,'kind':'backup','verified':True,'description':'Opération exécutée sur le banc synthétique local ; aucune garantie de reprise hors site.', 'last_'+kind:details}
        row.status='verified_local';row.updated_at=now


def inventory_proof(sessions, payload):
    from app.domain_models import DomainRecord
    from sqlalchemy import select
    if set(payload)!={'at','components','application_source_sha256'} or len(payload['components'])>15:raise ValueError('Invalid inventory evidence')
    now=datetime.now(timezone.utc).timestamp()
    with sessions.begin() as db:
        for component in payload['components']:
            if not re.fullmatch(r'[a-z]{1,20}',component['service']):raise ValueError('Invalid component service')
            ident='component-'+('api' if component['service']=='app' else component['service'])
            row=db.get(DomainRecord,ident)
            if row is None:
                row=DomainRecord(id=ident,kind='component',data={},created_at=now,updated_at=now);db.add(row)
            row.status='observed_local';row.updated_at=now
            row.data={**component,'title':component['service'].upper(),'end_of_support':'unknown','observed_at':payload['at']}
        mouse=db.get(DomainRecord,'component-mouse')
        if mouse:
            versions=sorted({row.data.get('firmware','unknown') for row in db.scalars(select(DomainRecord).where(DomainRecord.kind=='device'))})
            mouse.data={'title':'Firmware déclaré des appareils synthétiques','version':', '.join(versions),'end_of_support':'unknown','source':'synthetic_device_registry','hardware_attested':False,'observed_at':payload['at']}
            mouse.updated_at=now
        proof=db.get(DomainRecord,'inventory-state')
        if proof is None:
            proof=DomainRecord(id='inventory-state',kind='proof',data={},created_at=now,updated_at=now);db.add(proof)
        proof.status='verified_local';proof.updated_at=now
        proof.data={'kind':'inventory','verified':True,'observed_at':payload['at'],'application_source_sha256':payload['application_source_sha256'],'component_count':len(payload['components']),'description':'Images et bibliothèques observées dans les conteneurs SKELIVIA ; aucun audit de vulnérabilités ni date de fin de support déduite.'}


def certificate_operation(sessions, payload):
    """Owner-only CLI adapter. No HTTP route and no handling of private key values."""
    from sqlalchemy import select
    from app.models import Account
    from app.domain_models import DomainJob,DomainRecord
    from app.transport_models import DeviceIdentity
    phase=payload.get('phase','plan')
    if phase not in ('plan','stage','complete'):raise ValueError('Invalid certificate operation phase')
    with sessions.begin() as db:
        job=db.scalar(select(DomainJob).where(DomainJob.id==payload['job_id']).with_for_update())
        if not job or job.kind!='certificate':raise ValueError('Validated certificate job required')
        actor=db.get(Account,job.owner_id)
        if not actor or actor.role!='security' or not actor.active:raise ValueError('Active security requester required')
        operation=job.payload.get('operation')
        device=db.get(DomainRecord,job.target_id)
        identity=db.scalar(select(DeviceIdentity).where(DeviceIdentity.device_id==job.target_id))
        if not device or device.kind!='device' or not identity or job.payload.get('device_id')!=device.id:raise ValueError('Certificate job/device mismatch')
        if operation not in ('revoke','renew'):raise ValueError('Unknown certificate operation')
        plan={'job_id':job.id,'operation':operation,'device_id':device.id,'cert_cn':identity.cert_cn,'cert_serial':identity.cert_serial,'status':job.status,'dry_run':phase=='plan'}
        if phase=='plan':return plan
        if operation!='revoke':raise ValueError('Renewal requires verified installation and pairing; no automatic completion')
        if job.status=='completed':return {**plan,'already_completed':True}
        if job.status not in ('pending','revocation_pending_disconnect'):raise ValueError('Certificate job is not pending')
        if payload.get('cert_serial')!=identity.cert_serial:raise ValueError('Certificate serial changed')
        now=datetime.now(timezone.utc).timestamp()
        if phase=='stage':
            identity.revoked_at=identity.revoked_at or now
            device.data={**device.data,'certificate':{**device.data.get('certificate',{}),'revoked':True,'revocation_scope':'application_ingestion'}}
            job.status='revocation_pending_disconnect';job.updated_at=now
            job.result={'status':job.status,'detail':'Révocation en base enregistrée ; coupure MQTT et test TLS encore requis.'}
        else:
            if job.status!='revocation_pending_disconnect' or identity.revoked_at is None or payload.get('tls_rejection_verified') is not True or not re.fullmatch(r'[a-f0-9]{64}',payload.get('crl_sha256','')):
                raise ValueError('Broker disconnect and verified TLS rejection proof required')
            evidence='certificate-proof-'+uuid4().hex
            job.status='completed';job.updated_at=now
            job.result={'status':'completed','detail':'Révocation appliquée en base et au broker ; certificat rejeté au test TLS.','evidence_id':evidence,'verified_at':now,'crl_sha256':payload['crl_sha256']}
            device.data={**device.data,'certificate':{**device.data.get('certificate',{}),'revoked':True,'revocation_scope':'application_and_broker_tls'},'history':[*device.data.get('history',[]),{'kind':'certificate_revoked','at':now,'evidence_id':evidence}]}
        return {**plan,'status':job.status,'dry_run':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['backup','restore','policy','reconcile','proof','inventory','certificate'])
    parser.add_argument('--file',type=Path)
    args=parser.parse_args()
    if args.action=='backup': backup()
    elif args.action=='restore':
        if not args.file: parser.error('--file is required')
        restore(args.file)
    elif args.action=='policy': print(json.dumps(current_policy(db_factory())))
    elif args.action=='proof':
        operation_proof(db_factory(),json.load(sys.stdin));print('{"status":"operation_recorded"}')
    elif args.action=='inventory':
        inventory_proof(db_factory(),json.load(sys.stdin));print('{"status":"inventory_recorded"}')
    elif args.action=='certificate':print(json.dumps(certificate_operation(db_factory(),json.load(sys.stdin))))
    else:
        target=os.environ.get('SKELIVIA_RESTORE_DATABASE','')
        if not RESTORE_NAME.fullmatch(target): raise ValueError('Isolated database required')
        reconcile(db_factory(target),json.load(sys.stdin))
        print('{"status":"reconciled"}')
