"""Private MQTT subscriber. Broker certificates + topic ACL establish publisher identity."""
import logging
import base64
from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import threading
import time
from uuid import UUID, uuid4
import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError
from typing import Literal
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from .ingestion import ingest, IngestionRejected, _unique_object
from .models import Account
from .domain_models import DomainRecord, DomainJob, DomainDiagnostic, SupportScope
from .transport_models import DeviceIdentity

LOG = logging.getLogger('skelivia.ingestion')
ACK_TOPIC = re.compile(r'^skelivia/v1/devices/([A-Za-z0-9_-]{1,80})/ack$')


class AckV1(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    schema_version: Literal['skelivia.ack.v1']
    synthetic: StrictBool
    job_id: str = Field(min_length=1,max_length=80)
    device_id: str = Field(min_length=1,max_length=80)
    kind: Literal['calibration','update']
    nonce: str = Field(pattern=r'^[a-f0-9]{64}$')
    status: Literal['succeeded','failed']
    proof_id: str
    measured_at: str
    calibration_version: str | None = Field(default=None,pattern=r'^[A-Za-z0-9._-]{1,40}$')
    firmware_version: str | None = Field(default=None,pattern=r'^[A-Za-z0-9._-]{1,40}$')
    artifact_sha256: str | None = Field(default=None,pattern=r'^[a-f0-9]{64}$')


def authorized_job(db, job, now):
    """Recheck rights at dispatch AND acknowledgement, not only browser request."""
    device=db.scalar(select(DomainRecord).where(DomainRecord.id==job.target_id,DomainRecord.kind=='device').with_for_update())
    if not device or device.owner_id!=job.owner_id or device.status in ('lost','revoked','deleted','replaced'):
        raise IngestionRejected('job_device_forbidden')
    owner=db.execute(select(Account.id,Account.role,Account.active).where(Account.id==job.owner_id)).first()
    if not owner or not owner.active or owner.role!='user':raise IngestionRejected('job_owner_inactive')
    identity=db.scalar(select(DeviceIdentity).where(DeviceIdentity.device_id==device.id))
    if not identity or identity.revoked_at is not None or (identity.expires_at is not None and identity.expires_at<=now):raise IngestionRejected('job_certificate_forbidden')
    certificate=device.data.get('certificate',{})
    if certificate.get('revoked') or certificate.get('serial')!=identity.cert_serial:raise IngestionRejected('job_certificate_changed')
    if job.assigned_to:
        support=db.execute(select(Account.id,Account.role,Account.active).where(Account.id==job.assigned_to)).first()
        scope=db.get(SupportScope,(job.assigned_to,device.org_id))
        ticket_id=job.payload.get('ticket_id')
        ticket=db.get(DomainRecord,ticket_id) if ticket_id else None
        diagnostic=db.get(DomainDiagnostic,ticket_id) if ticket_id else None
        if not support or not support.active or support.role!='support' or not scope or not scope.active:
            raise IngestionRejected('job_support_scope_forbidden')
        if not ticket or ticket.kind!='ticket' or ticket.assigned_to!=job.assigned_to or ticket.owner_id!=job.owner_id or ticket.device_id!=device.id or ticket.status=='resolved':
            raise IngestionRejected('job_ticket_forbidden')
        if not diagnostic or not diagnostic.active or diagnostic.expires<=now or diagnostic.support_id!=job.assigned_to or diagnostic.device_id!=device.id or diagnostic.owner_id!=job.owner_id:
            raise IngestionRejected('job_diagnostic_expired')
    elif job.kind!='calibration':
        raise IngestionRejected('job_support_required')
    if job.kind=='update':
        patch=db.get(DomainRecord,job.payload.get('patch_id'))
        if not patch or patch.kind!='patch' or patch.status!='approved' or patch.data.get('version')!=job.payload.get('version'):
            raise IngestionRejected('job_patch_not_approved')
    return device,identity


def verified_artifact(patch_id, version, root=None):
    root=Path(root or os.environ.get('SKELIVIA_FIRMWARE_DIR','/run/firmware')).resolve()
    manifest=json.loads((root/'manifest.json').read_text())
    item=next((entry for entry in manifest['artifacts'] if entry['patch_id']==patch_id and entry['version']==version),None)
    if not item or item.get('synthetic') is not True:raise IngestionRejected('unsigned_or_real_artifact')
    path=(root/item['file']).resolve()
    if not path.is_relative_to(root):raise IngestionRejected('artifact_path_forbidden')
    blob=path.read_bytes()
    if len(blob)>1024*1024 or sha256(blob).hexdigest()!=item['sha256']:raise IngestionRejected('artifact_digest_mismatch')
    key=serialization.load_pem_public_key((root/'signing-public.pem').read_bytes())
    if not isinstance(key,Ed25519PublicKey):raise IngestionRejected('artifact_key_invalid')
    signed=json.dumps({k:item[k] for k in ('patch_id','version','sha256','synthetic')},sort_keys=True,separators=(',',':')).encode()
    try:key.verify(base64.b64decode(item['signature'],validate=True),signed)
    except Exception:raise IngestionRejected('artifact_signature_invalid') from None
    return {k:item[k] for k in ('sha256','signature','version','synthetic')}


def pending_commands(sessions, *, now=None, artifact_root=None):
    now=time.time() if now is None else now
    commands=[]
    with sessions.begin() as db:
        jobs=list(db.scalars(select(DomainJob).where(DomainJob.kind.in_(['calibration','update']),DomainJob.status.in_(['pending','sent'])).order_by(DomainJob.created_at).limit(20).with_for_update(skip_locked=True)))
        for job in jobs:
            if job.status=='sent':
                if job.result.get('deadline',0)<=now:
                    job.status='expired';job.updated_at=now;job.result={'status':'expired','detail':'Aucun accusé authentifié reçu dans le délai.'}
                continue
            try:
                device,identity=authorized_job(db,job,now)
                artifact=verified_artifact(job.payload['patch_id'],job.payload['version'],artifact_root) if job.kind=='update' else None
            except (IngestionRejected,OSError,ValueError,KeyError) as error:
                job.status='blocked';job.updated_at=now;job.result={'status':'blocked','detail':str(error) if isinstance(error,IngestionRejected) else 'artifact_unavailable'}
                continue
            nonce=secrets.token_hex(32);deadline=now+120
            packet={'schema_version':'skelivia.command.v1','synthetic':True,'job_id':job.id,'device_id':device.id,'kind':job.kind,'nonce':nonce,'deadline':deadline}
            if artifact:packet['artifact']=artifact
            job.status='sent';job.updated_at=now
            job.result={'status':'sent','command_nonce':nonce,'deadline':deadline,'device_cn':identity.cert_cn,'artifact_sha256':artifact['sha256'] if artifact else None}
            commands.append(('skelivia/v1/devices/'+identity.cert_cn+'/commands',json.dumps(packet,separators=(',',':')).encode()))
    return commands


def accept_ack(sessions,topic,payload,*,retained=False,now=None,artifact_root=None):
    now=time.time() if now is None else now
    match=ACK_TOPIC.fullmatch(topic)
    if not match or retained or len(payload)>4096:raise IngestionRejected('invalid_ack_transport')
    try:
        ack=AckV1.model_validate(json.loads(payload,object_pairs_hook=_unique_object))
        if ack.synthetic is not True:raise ValueError('real_ack_forbidden')
        if str(UUID(ack.proof_id))!=ack.proof_id:raise ValueError('invalid_proof_id')
        observed=datetime.fromisoformat(ack.measured_at.replace('Z','+00:00'))
        if observed.tzinfo is None or observed.utcoffset().total_seconds()!=0 or not -30<=now-observed.timestamp()<=120:raise ValueError('stale_ack')
    except (ValueError,ValidationError,TypeError,UnicodeError):raise IngestionRejected('invalid_ack_schema') from None
    with sessions.begin() as db:
        job=db.scalar(select(DomainJob).where(DomainJob.id==ack.job_id).with_for_update())
        if not job or job.status!='sent' or job.kind!=ack.kind or job.target_id!=ack.device_id:raise IngestionRejected('ack_job_mismatch')
        proof=job.result
        if proof.get('device_cn')!=match[1] or proof.get('deadline',0)<=now or not hmac.compare_digest(proof.get('command_nonce',''),ack.nonce):raise IngestionRejected('ack_nonce_or_deadline')
        device,identity=authorized_job(db,job,now)
        if identity.cert_cn!=match[1]:raise IngestionRejected('ack_certificate_mismatch')
        if ack.status=='succeeded' and job.kind=='calibration' and not ack.calibration_version:raise IngestionRejected('ack_calibration_missing')
        if job.kind=='update':
            artifact=verified_artifact(job.payload['patch_id'],job.payload['version'],artifact_root)
            if ack.status=='succeeded' and (ack.firmware_version!=job.payload['version'] or ack.artifact_sha256!=artifact['sha256'] or ack.artifact_sha256!=proof.get('artifact_sha256')):raise IngestionRejected('ack_artifact_mismatch')
        job.status='completed' if ack.status=='succeeded' else 'failed';job.updated_at=now
        job.result={'status':job.status,'detail':'Accusé du banc synthétique authentifié ; aucune validation physique.', 'verified_at':datetime.fromtimestamp(now,timezone.utc).isoformat(),'evidence_id':ack.proof_id,'synthetic':True}
        if ack.status=='succeeded':
            data=dict(device.data)
            if job.kind=='calibration':data.update(calibration=ack.calibration_version,calibration_status='synthetic_reference')
            else:data.update(firmware=ack.firmware_version,calibration_status='required')
            data['history']=[*data.get('history',[]),{'kind':job.kind,'at':now,'job_id':job.id,'evidence_id':ack.proof_id,'synthetic':True}]
            device.data=data;device.updated_at=now
            db.add(DomainRecord(id='notification-'+uuid4().hex,kind='notification',owner_id=job.owner_id,status='unread',data={'title':'État technique de votre appareil mis à jour','route':'device','kind':'calibration' if job.kind=='calibration' else 'device','synthetic':True},created_at=now,updated_at=now))
        return job.id


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    url = Path(os.environ['SKELIVIA_DATABASE_URL_FILE']).read_text().strip()
    engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='skelivia-ingestion', protocol=mqtt.MQTTv5, manual_ack=True)
    tls = ssl.create_default_context(cafile=os.environ['SKELIVIA_MQTT_CA_FILE'])
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(os.environ['SKELIVIA_MQTT_CERT_FILE'], os.environ['SKELIVIA_MQTT_KEY_FILE'])
    client.tls_set_context(tls)
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    def connected(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            LOG.error('broker_connection_refused')
            return
        client.subscribe('skelivia/v1/devices/+/telemetry', qos=1)
        client.subscribe('skelivia/v1/devices/+/ack', qos=1)
        LOG.info('broker_connected')

    def received(client, userdata, message):
        try:
            if message.topic.endswith('/ack'):
                accept_ack(sessions,message.topic,message.payload,retained=message.retain)
            else:
                ingest(sessions, message.topic, message.payload, retained=message.retain)
            LOG.info('ingestion_accepted')
        except IngestionRejected as error:
            LOG.warning('ingestion_rejected reason=%s', error)
        except Exception:
            # Do not acknowledge transient storage failure: broker will redeliver.
            LOG.error('ingestion_storage_failure')
            client.disconnect()
            raise
        if message.qos:
            client.ack(message.mid, message.qos)

    client.on_connect = connected
    client.on_message = received
    def dispatch():
        last_monitor=0
        while True:
            if time.monotonic()-last_monitor>=30:
                try:
                    from .security_monitor import tick
                    tick(sessions,client.is_connected())
                except Exception:
                    LOG.error('security_monitor_failed')
                last_monitor=time.monotonic()
            if client.is_connected():
                try:
                    for topic,payload in pending_commands(sessions):
                        client.publish(topic,payload,qos=1,retain=False)
                except Exception:
                    LOG.error('command_dispatch_failed')
            time.sleep(1)
    threading.Thread(target=dispatch,name='command-dispatch',daemon=True).start()
    properties=mqtt.Properties(mqtt.PacketTypes.CONNECT)
    properties.SessionExpiryInterval=86400
    client.connect(os.getenv('SKELIVIA_MQTT_HOST', 'broker'), int(os.getenv('SKELIVIA_MQTT_PORT', '8883')), keepalive=30, clean_start=False, properties=properties)
    client.loop_forever(retry_first_connection=True)


if __name__ == '__main__':
    main()
