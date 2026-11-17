"""Opt-in Web Push with an owner-scoped outbox and generic notifications only.

No external send occurs unless deployment explicitly enables it and supplies VAPID.
"""
import argparse
import base64
from datetime import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import time
from typing import Annotated
from urllib.parse import urlsplit
import uuid
from zoneinfo import ZoneInfo
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from .database import configure_actor, runtime_url
from .models import Account
from .domain_models import DomainRecord
from .push_models import PushSubscription as Subscription, PushDelivery as Delivery, PushSchedule as Schedule

ALLOWED_KINDS={'pause','advice','report','support','calibration'}
VENDORS={'fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com'}
TERMINAL={'accepted_by_provider','expired','cancelled','quiet_suppressed','channel_disabled','unsupported_watch_only','failed','revoked'}


def b64decode(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+={0,2}',value):raise ValueError('Clé base64url invalide.')
    return base64.urlsafe_b64decode(value+'='*((-len(value))%4))


def validate_endpoint(value,resolve=False):
    if not isinstance(value,str) or not 1<=len(value)<=2048 or any(ord(c)<=32 for c in value):raise ValueError('Endpoint invalide.')
    u=urlsplit(value)
    host=u.hostname or ''
    if u.scheme!='https' or u.username or u.password or u.fragment or u.port not in (None,443) or not u.path or u.netloc!=host and u.netloc!=host+':443':raise ValueError('Endpoint HTTPS strict requis.')
    if host not in VENDORS and not re.fullmatch(r'[a-z0-9-]+\.notify\.windows\.com',host):raise ValueError('Fournisseur de notifications non autorisé.')
    if resolve:
        addresses={row[4][0] for row in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):raise ValueError('Adresse réseau non publique refusée.')
    return value


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)


class Keys(Strict):
    p256dh: Annotated[str,StringConstraints(min_length=80,max_length=100)]
    auth: Annotated[str,StringConstraints(min_length=20,max_length=30)]

    @field_validator('p256dh')
    @classmethod
    def key_valid(cls,value):
        raw=b64decode(value)
        if len(raw)!=65:raise ValueError('Clé P-256 invalide.')
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),raw)
        return value

    @field_validator('auth')
    @classmethod
    def auth_valid(cls,value):
        if len(b64decode(value))!=16:raise ValueError('Secret auth invalide.')
        return value


class Subscribe(Strict):
    endpoint: Annotated[str,StringConstraints(min_length=1,max_length=2048)]
    keys: Keys
    label: Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=80)]='Ce téléphone'

    @field_validator('endpoint')
    @classmethod
    def endpoint_valid(cls,value):return validate_endpoint(value)


class Unsubscribe(Strict):
    id: Annotated[str,StringConstraints(min_length=1,max_length=80,pattern=r'^[a-zA-Z0-9-]+$')]


def vapid_config():
    enabled=os.getenv('SKELIVIA_PUSH_ENABLED','false').lower()=='true'
    private=os.getenv('SKELIVIA_VAPID_PRIVATE_KEY_FILE','')
    public=os.getenv('SKELIVIA_VAPID_PUBLIC_KEY_FILE','')
    subject=os.getenv('SKELIVIA_VAPID_SUBJECT','')
    if not enabled:return {'configured':False,'public_key':None,'reason':'Envoi externe désactivé. Un déploiement HTTPS accessible au téléphone et un contact VAPID réel sont requis.'}
    if not private or not public or not Path(private).is_file() or not Path(public).is_file():return {'configured':False,'public_key':None,'reason':'Clés VAPID non configurées.'}
    if not re.fullmatch(r'mailto:[^@\s<>]{1,120}@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}',subject):return {'configured':False,'public_key':None,'reason':'Contact VAPID réel requis (mailto).'}
    try:
        key=serialization.load_pem_private_key(Path(private).read_bytes(),password=None)
        public_key=Path(public).read_text().strip()
        if not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1):raise ValueError('curve')
        if b64decode(public_key)!=key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint):raise ValueError('mismatch')
    except (ValueError,TypeError,OSError):return {'configured':False,'public_key':None,'reason':'Paire VAPID invalide.'}
    return {'configured':True,'public_key':public_key,'reason':None}


def require_user(a):
    if a.role!='user' or not a.active:raise HTTPException(404,'Ressource indisponible.')


def install_push(app,factory,account_dep,csrf_dep):
    def db_dep(a=Depends(account_dep)):
        require_user(a)
        with factory() as db:
            configure_actor(db,a)
            yield db

    @app.get('/api/push/config')
    def config(a=Depends(account_dep),db=Depends(db_dep)):
        subscriptions=db.scalars(select(Subscription).where(Subscription.owner_id==a.id)).all()
        deliveries=db.scalars(select(Delivery).where(Delivery.owner_id==a.id).order_by(Delivery.created_at.desc()).limit(100)).all()
        return {**vapid_config(),'watch':'os_mirroring_only','subscriptions':[{'id':s.id,'label':s.label,'active':s.active,'created_at':s.created_at} for s in subscriptions],'deliveries':[{'id':d.id,'kind':d.kind,'status':d.status,'attempts':d.attempts,'updated_at':d.updated_at} for d in deliveries]}

    @app.post('/api/push/subscribe',dependencies=[Depends(csrf_dep)])
    def subscribe(body:Subscribe,a=Depends(account_dep),db=Depends(db_dep)):
        if not vapid_config()['configured']:raise HTTPException(409,'Web Push non configuré ; aucun abonnement serveur activé.')
        digest=hashlib.sha256(body.endpoint.encode()).hexdigest()
        existing=db.scalar(select(Subscription).where(Subscription.endpoint_hash==digest))
        if existing and existing.owner_id!=a.id:raise HTTPException(409,'Cet abonnement ne peut pas être réattribué.')
        now=time.time()
        if not existing or not existing.active:
            if len(db.scalars(select(Subscription.id).where(Subscription.owner_id==a.id,Subscription.active.is_(True))).all())>=8:raise HTTPException(409,'Limite de huit abonnements actifs atteinte.')
        if not existing:
            existing=Subscription(id='push-'+uuid.uuid4().hex,owner_id=a.id,endpoint_hash=digest,label=body.label,data={'endpoint':body.endpoint,'keys':body.keys.model_dump()},active=True,created_at=now,updated_at=now);db.add(existing)
        else:
            if not existing.active:existing.created_at=now
            existing.data={'endpoint':body.endpoint,'keys':body.keys.model_dump()};existing.label=body.label;existing.active=True;existing.updated_at=now
        try:db.commit()
        except IntegrityError:
            db.rollback();raise HTTPException(409,'Cet abonnement est déjà enregistré ; aucune réattribution effectuée.') from None
        return {'ok':True,'id':existing.id}

    @app.post('/api/push/unsubscribe',dependencies=[Depends(csrf_dep)])
    def unsubscribe(body:Unsubscribe,a=Depends(account_dep),db=Depends(db_dep)):
        s=db.get(Subscription,body.id)
        if not s or s.owner_id!=a.id:raise HTTPException(404,'Abonnement indisponible.')
        s.active=False;s.updated_at=time.time();db.commit();return {'ok':True}


def preferences(db,owner):
    r=db.scalar(select(DomainRecord).where(DomainRecord.kind=='settings',DomainRecord.owner_id==owner).order_by(DomainRecord.updated_at.desc()).execution_options(populate_existing=True))
    return r.data if r else {}


def quiet(settings,now):
    current=datetime.fromtimestamp(now,ZoneInfo(os.getenv('SKELIVIA_TIMEZONE','Europe/Paris'))).strftime('%H:%M')
    start=settings.get('quiet_start','19:00');end=settings.get('quiet_end','08:00')
    return start<=current<end if start<end else current>=start or current<end if start>end else False


def generic_payload(kind):
    if kind not in ALLOWED_KINDS:raise ValueError('Notification non autorisée pour un canal externe.')
    return {'kind':kind,'title':'SKELIVIA','body':'Une information est disponible dans votre espace.','url':'/?notifications=1','silent':False}


def send_webpush(subscription,payload):
    """Production transport. No redirects, proxy environment, private host or raw error log."""
    from pywebpush import webpush, WebPushException
    import requests
    class SafeSession(requests.Session):
        def __init__(self):super().__init__();self.trust_env=False
        def request(self,method,url,**kwargs):
            if method.upper()!='POST' or url!=subscription['endpoint']:raise ValueError('Destination refusée.')
            validate_endpoint(url,resolve=True)
            kwargs.update(allow_redirects=False,verify=True,timeout=10)
            return super().request(method,url,**kwargs)
    validate_endpoint(subscription['endpoint'],resolve=True)
    with SafeSession() as transport:
        try:
            response=webpush(subscription_info=subscription,data=json.dumps(payload,separators=(',',':')),vapid_private_key=os.environ['SKELIVIA_VAPID_PRIVATE_KEY_FILE'],vapid_claims={'sub':os.environ['SKELIVIA_VAPID_SUBJECT']},ttl=60,timeout=10,content_encoding='aes128gcm',requests_session=transport,verbose=False)
            return response.status_code
        except WebPushException as exc:return exc.status_code or 503


def schedule_pause(db,a,settings,now):
    schedule=db.get(Schedule,a.id)
    interval=max(5,min(180,int(settings.get('pause_minutes',45))))*60
    if not settings.get('pause_enabled',False):
        if schedule:schedule.next_pause=now+interval
        return
    if not schedule:
        db.add(Schedule(owner_id=a.id,next_pause=max(now+interval,settings.get('snoozed_until',0))));return
    if schedule.next_pause>now or settings.get('snoozed_until',0)>now:return
    db.add(DomainRecord(id='notice-'+uuid.uuid4().hex,kind='notification',owner_id=a.id,status='active',data={'kind':'pause','title':'Un rappel de pause est disponible.','route':'settings','read':False},created_at=now,updated_at=now))
    schedule.next_pause=now+interval


def process_owner(db,a,now,transport=send_webpush,enabled=None):
    """Called within an owner-specific transaction; transport is mocked in tests."""
    configure_actor(db,a)
    # Refresh identity at dispatch, not only when the subscription was created.
    db.refresh(a,attribute_names=['id','role','org_id','patient_id','active'])
    if not a.active or a.role!='user':return 0
    settings=preferences(db,a.id)
    schedule_pause(db,a,settings,now);db.flush()
    subscriptions=list(db.scalars(select(Subscription).where(Subscription.owner_id==a.id,Subscription.active.is_(True))))
    notices=list(db.scalars(select(DomainRecord).where(DomainRecord.kind=='notification',DomainRecord.owner_id==a.id,DomainRecord.created_at>=now-86400)))
    for n in notices:
        kind=n.data.get('kind')
        if kind not in ALLOWED_KINDS:continue  # Login/security notifications never leave the dashboard.
        for s in subscriptions:
            if n.created_at<s.created_at:continue  # No backfill to a newly shared browser.
            if not db.scalar(select(Delivery.id).where(Delivery.notification_id==n.id,Delivery.subscription_id==s.id)):
                db.add(Delivery(id='delivery-'+uuid.uuid4().hex,owner_id=a.id,notification_id=n.id,subscription_id=s.id,kind=kind,status='pending',attempts=0,next_attempt=now,created_at=now,updated_at=now))
    db.flush()
    ready=list(db.scalars(select(Delivery).where(Delivery.owner_id==a.id,Delivery.status.in_(['pending','retry','configuration_required']),Delivery.next_attempt<=now).with_for_update(skip_locked=True).limit(50)))
    configured=vapid_config()['configured'] if enabled is None else enabled
    sent=0
    for delivery in ready:
        delivery.updated_at=now
        s=db.get(Subscription,delivery.subscription_id);n=db.get(DomainRecord,delivery.notification_id)
        db.refresh(a,attribute_names=['id','role','org_id','patient_id','active'])
        if s:db.refresh(s,attribute_names=['active','owner_id','data'])
        if n:db.refresh(n,attribute_names=['owner_id','data'])
        settings=preferences(db,a.id)
        if not a.active or a.role!='user' or not s or not s.active or s.owner_id!=a.id or not n or n.owner_id!=a.id or n.data.get('read') or n.data.get('kind')!=delivery.kind:
            delivery.status='cancelled';continue
        if now-n.created_at>86400:delivery.status='expired';continue
        channel=settings.get('channels',{}).get(delivery.kind,'none')
        if channel=='watch':delivery.status='unsupported_watch_only';continue
        if channel not in {'phone','both'}:delivery.status='channel_disabled';continue
        if quiet(settings,now):delivery.status='quiet_suppressed';continue
        if delivery.kind=='pause' and (not settings.get('pause_enabled') or settings.get('snoozed_until',0)>now):delivery.status='cancelled';continue
        if not configured:delivery.status='configuration_required';delivery.next_attempt=now+300;continue
        delivery.attempts+=1
        try:
            # Revalidate stored subscription at dispatch; encrypted storage is not a trust boundary.
            Subscribe.model_validate({**s.data,'label':s.label})
            code=int(transport(s.data,generic_payload(delivery.kind)))
        except Exception:
            code=503  # Never persist exception strings: they may contain a token or provider body.
        delivery.provider_status=code
        if 200<=code<=202:delivery.status='accepted_by_provider';sent+=1
        elif code in {404,410}:delivery.status='revoked';s.active=False;s.updated_at=now
        elif (code==429 or code>=500) and delivery.attempts<3:
            delivery.status='retry';delivery.next_attempt=now+60*(2**(delivery.attempts-1))
        else:delivery.status='failed'
    return sent


def run_cycle(factory,transport=send_webpush):
    with factory() as db:
        # The dedicated push SQL role receives only these non-medical account columns.
        accounts=list(db.execute(select(Account.id,Account.role,Account.org_id,Account.patient_id,Account.active)).all())
    count=0
    for entry in accounts:
        if not entry.active or entry.role!='user':continue
        with factory() as db:
            from sqlalchemy.orm import load_only
            a=db.scalar(select(Account).options(load_only(Account.id,Account.role,Account.org_id,Account.patient_id,Account.active)).where(Account.id==entry.id))
            configure_actor(db,a)
            try:count+=process_owner(db,a,time.time(),transport);db.commit()
            except IntegrityError:db.rollback()  # Concurrent enqueue; unique outbox key wins.
    return count


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--loop',action='store_true');args=parser.parse_args()
    engine=create_engine(runtime_url(),hide_parameters=True,pool_pre_ping=True);factory=sessionmaker(engine,expire_on_commit=False)
    try:
        while True:
            run_cycle(factory)
            if not args.loop:break
            time.sleep(30)
    finally:engine.dispose()


if __name__=='__main__':main()
