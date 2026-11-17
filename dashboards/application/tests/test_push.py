"""No provider contact: transport is mocked, ownership and payload limits are real."""
import base64
from datetime import datetime, timezone
import time
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, text
from app.database import database
from app.models import Account
from app.domain_models import DomainRecord as R
from app.push_models import PushSubscription as S, PushDelivery as D
from app.push import install_push, Subscribe, validate_endpoint, process_owner, generic_payload, quiet


def encoded(value):return base64.urlsafe_b64encode(value).decode().rstrip('=')


@pytest.fixture
def push_bank(tmp_path,monkeypatch):
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(tmp_path/'data.key'))
    private=ec.generate_private_key(ec.SECP256R1())
    keyfile=tmp_path/'vapid.pem';publicfile=tmp_path/'vapid.pub'
    keyfile.write_bytes(private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    publicfile.write_text(encoded(private.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)))
    monkeypatch.setenv('SKELIVIA_VAPID_PRIVATE_KEY_FILE',str(keyfile));monkeypatch.setenv('SKELIVIA_VAPID_PUBLIC_KEY_FILE',str(publicfile))
    monkeypatch.setenv('SKELIVIA_VAPID_SUBJECT','mailto:test@example.invalid');monkeypatch.setenv('SKELIVIA_PUSH_ENABLED','true')
    engine,factory=database('sqlite:///'+(tmp_path/'push.db').as_posix())
    with factory() as db:
        for uid,role in [('a','user'),('b','user'),('s','support')]:db.add(Account(id=uid,username=uid,name=uid,role=role,org_id='org',patient_id='p-'+uid if role=='user' else None,password_hash='not-a-login',otp_secret='DISABLED',active=True))
        db.commit()
    app=FastAPI()
    def actor(request:Request):
        with factory() as db:return db.get(Account,request.headers['x-test-owner'])
    def csrf(request:Request):
        if request.headers.get('x-test-csrf')!='yes':raise HTTPException(403)
    install_push(app,factory,actor,csrf)
    clients=[]
    def client(owner):
        c=TestClient(app);c.headers.update({'x-test-owner':owner,'x-test-csrf':'yes'});clients.append(c);return c
    public=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
    subscription={'endpoint':'https://fcm.googleapis.com/fcm/send/qa-endpoint','keys':{'p256dh':encoded(public),'auth':encoded(b'0123456789abcdef')},'label':'Téléphone QA'}
    yield factory,client,subscription
    for c in clients:c.close()
    engine.dispose()


def add_notice(db,kind,now,owner='a',read=False):
    n=R(id='n-'+kind,kind='notification',owner_id=owner,status='active',created_at=now,updated_at=now,data={'kind':kind,'title':'PRIVATE HEALTH TITLE NEVER PUSH','body':'PRIVATE MEDICAL CONTENT','route':'documents','read':read});db.add(n)
    return n


def add_settings(db,channels,**extra):
    db.add(R(id='prefs',kind='settings',owner_id='a',created_at=0,updated_at=0,status='active',data={'channels':channels,'quiet_start':'00:00','quiet_end':'00:00',**extra}))


def test_subscription_owner_secret_crypto_and_csrf(push_bank):
    factory,client,sub=push_bank;a=client('a');b=client('b')
    first=a.post('/api/push/subscribe',json=sub);assert first.status_code==200
    assert b.post('/api/push/subscribe',json=sub).status_code==409
    assert b.post('/api/push/unsubscribe',json={'id':first.json()['id']}).status_code==404
    assert client('s').get('/api/push/config').status_code==404
    response=a.get('/api/push/config');assert sub['endpoint'] not in response.text and sub['keys']['auth'] not in response.text
    assert a.post('/api/push/unsubscribe',json={'id':first.json()['id']},headers={'x-test-csrf':'no'}).status_code==403
    with factory() as db:
        raw=db.execute(text('select data from push_subscriptions')).scalar();assert raw.startswith('v1:') and 'qa-endpoint' not in raw
    assert a.post('/api/push/unsubscribe',json={'id':first.json()['id']}).status_code==200


@pytest.mark.parametrize('url',['http://fcm.googleapis.com/a','https://127.0.0.1/a','https://localhost/a','https://evil.test/a','https://fcm.googleapis.com.evil.test/a','https://user@fcm.googleapis.com/a','https://fcm.googleapis.com:444/a','https://fcm.googleapis.com/a#fragment','https://fcm.googleapis.com\\@127.0.0.1/a'])
def test_ssrf_and_redirect_destinations_rejected(url):
    with pytest.raises(ValueError):validate_endpoint(url)


def test_invalid_key_and_extra_owner_rejected(push_bank):
    _,client,sub=push_bank
    assert client('a').post('/api/push/subscribe',json={**sub,'owner_id':'b'}).status_code==422
    with pytest.raises(ValidationError):Subscribe.model_validate({**sub,'keys':{**sub['keys'],'auth':encoded(b'short')}})


def test_generic_payload_and_login_never_push(push_bank):
    factory,client,sub=push_bank;client('a').post('/api/push/subscribe',json=sub)
    now=time.time()+2;sent=[]
    with factory() as db:
        add_settings(db,{'advice':'phone','connection':'both'});add_notice(db,'advice',now);add_notice(db,'connection',now);db.commit()
    with factory() as db:
        count=process_owner(db,db.get(Account,'a'),now+1,lambda subscription,payload:sent.append(payload) or 201,enabled=True);db.commit()
        assert count==1 and len(sent)==1
        assert sent[0]==generic_payload('advice')
        assert 'PRIVATE' not in str(sent) and 'patient' not in str(sent)
        assert db.scalar(select(D)).status=='accepted_by_provider'


def test_quiet_channel_changes_and_revoked_account_prevent_send(push_bank):
    factory,client,sub=push_bank;client('a').post('/api/push/subscribe',json=sub)
    now=datetime(2026,11,14,22,0,tzinfo=timezone.utc).timestamp()
    with factory() as db:
        subscription=db.scalar(select(S));subscription.created_at=now-5
        add_settings(db,{'advice':'phone'},quiet_start='19:00',quiet_end='08:00');add_notice(db,'advice',now);db.commit()
    calls=[]
    with factory() as db:
        process_owner(db,db.get(Account,'a'),now+1,lambda *args:calls.append(args) or 201,enabled=True);db.commit()
        assert db.scalar(select(D)).status=='quiet_suppressed'
    assert not calls
    with factory() as db:
        db.get(Account,'a').active=False;db.commit()
    with factory() as db:assert process_owner(db,db.get(Account,'a'),now+2,lambda *args:pytest.fail('must not send'),enabled=True)==0


def test_retries_are_bounded_and_410_deactivates(push_bank):
    factory,client,sub=push_bank;client('a').post('/api/push/subscribe',json=sub)
    now=time.time()+2
    with factory() as db:add_settings(db,{'advice':'both','support':'phone'});add_notice(db,'advice',now);db.commit()
    for elapsed in [1,62,183]:
        with factory() as db:process_owner(db,db.get(Account,'a'),now+elapsed,lambda *args:503,enabled=True);db.commit()
    with factory() as db:
        delivery=db.scalar(select(D));assert delivery.attempts==3 and delivery.status=='failed'
        add_notice(db,'support',now+184);db.commit()
    with factory() as db:
        process_owner(db,db.get(Account,'a'),now+185,lambda *args:410,enabled=True);db.commit()
        assert not db.scalar(select(S)).active


def test_disabled_configuration_never_calls_transport(push_bank,monkeypatch):
    factory,client,sub=push_bank;client('a').post('/api/push/subscribe',json=sub)
    now=time.time()+2
    monkeypatch.setenv('SKELIVIA_PUSH_ENABLED','false')
    assert client('a').get('/api/push/config').json()['configured'] is False
    with factory() as db:add_settings(db,{'advice':'phone'});add_notice(db,'advice',now);db.commit()
    with factory() as db:
        process_owner(db,db.get(Account,'a'),now+1,lambda *args:pytest.fail('No send authorized'));db.commit()
        assert db.scalar(select(D)).status=='configuration_required'


def test_watch_only_not_falsely_delivered_to_phone(push_bank):
    factory,client,sub=push_bank;client('a').post('/api/push/subscribe',json=sub)
    now=time.time()+2
    with factory() as db:add_settings(db,{'advice':'watch'});add_notice(db,'advice',now);db.commit()
    with factory() as db:
        process_owner(db,db.get(Account,'a'),now+1,lambda *args:pytest.fail('watch-only must not become phone'),enabled=True);db.commit()
        assert db.scalar(select(D)).status=='unsupported_watch_only'


def test_private_dns_answer_refused(monkeypatch):
    monkeypatch.setattr('app.push.socket.getaddrinfo',lambda *args,**kwargs:[(2,1,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError):validate_endpoint('https://fcm.googleapis.com/fcm/send/qa',resolve=True)


def test_changed_channel_cancels_retry(push_bank):
    factory,client,sub=push_bank;client('a').post('/api/push/subscribe',json=sub)
    now=time.time()+2
    with factory() as db:add_settings(db,{'advice':'phone'});add_notice(db,'advice',now);db.commit()
    with factory() as db:process_owner(db,db.get(Account,'a'),now+1,lambda *args:503,enabled=True);db.commit()
    with factory() as db:
        prefs=db.get(R,'prefs');prefs.data={**prefs.data,'channels':{'advice':'none'}};db.commit()
    with factory() as db:
        process_owner(db,db.get(Account,'a'),now+62,lambda *args:pytest.fail('Preference revocation must stop retry'),enabled=True);db.commit()
        assert db.scalar(select(D)).status=='channel_disabled'


@pytest.mark.parametrize('channel,quiet_hours,configured,expected',[
    ('phone',False,True,'accepted_by_provider'),
    ('none',False,True,'channel_disabled'),
    ('phone',True,True,'quiet_suppressed'),
    ('phone',False,False,'configuration_required'),
    ('watch',False,True,'unsupported_watch_only'),
])
def test_usage_bridge_uses_existing_pause_preferences_and_never_pushes_other_events(push_bank,channel,quiet_hours,configured,expected):
    from app.ingestion import UsageEventV1
    from app.usage_events import record_usage_events
    factory,client,sub=push_bank;client('a').post('/api/push/subscribe',json=sub)
    now=datetime(2026,11,14,22,0,tzinfo=timezone.utc).timestamp();sent=[]
    with factory.begin() as db:
        db.scalar(select(S)).created_at=now-5
        add_settings(db,{'pause':channel},pause_enabled=True,quiet_start='19:00' if quiet_hours else '00:00',quiet_end='08:00' if quiet_hours else '00:00')
        device=R(id='usage-device',kind='device',owner_id='a',patient_id='p-a',data={},created_at=0,updated_at=0);db.add(device);db.flush()
        events=[UsageEventV1(kind=kind,at_seconds=4.,origin='manual') for kind in ('pause_reminder','high_force','quiet_contact','absent')]
        assert all(e['status']=='notification_created' for e in record_usage_events(db,device,events,now))
    with factory.begin() as db:
        process_owner(db,db.get(Account,'a'),now+1,lambda subscription,payload:sent.append(payload) or 201,enabled=configured)
    with factory() as db:
        deliveries=list(db.scalars(select(D)))
        assert len(deliveries)==1 and deliveries[0].kind=='pause' and deliveries[0].status==expected
        assert len(list(db.scalars(select(R).where(R.kind=='notification'))))==4
    assert sent==([generic_payload('pause')] if expected=='accepted_by_provider' else [])
