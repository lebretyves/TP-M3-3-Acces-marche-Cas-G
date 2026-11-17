import time
import pytest
import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import create_app, COOKIE, hashed
from app.models import Account, CareLink, Report, Share, WebSession
from app.seed import seed

BASE='http://127.0.0.1:8766'


@pytest.fixture
def bank(database_url):
    app=create_app(database_url,testing=True)
    secrets={c['username']:c for c in seed(app.state.factory)}
    clients=[]
    def client(username=None):
        c=TestClient(app,base_url=BASE);clients.append(c)
        initial=c.get('/api/session').json()
        c.headers.update({'Origin':BASE,'X-CSRF-Token':initial['csrf_token']})
        if username:
            cred=secrets[username]
            resp=c.post('/api/login',json={'username':username,'password':cred['password'],'otp':pyotp.TOTP(cred['otp_secret']).now()})
            assert resp.status_code==200,resp.text
            c.headers['X-CSRF-Token']=resp.json()['csrf_token']
        return c
    yield app,client,secrets
    for c in clients:c.close()
    app.state.engine.dispose()


def grant(c):
    r=c.post('/api/shares',json={'report_id':'r-alice-01','clinician_id':'c-lina','duration_hours':24})
    assert r.status_code==200,r.text
    return r.json()['id']


def test_anonymous_never_reads_bilan(bank):
    _,client,_=bank;c=client()
    for path in ['/api/dashboard','/api/reports/r-alice-01','/api/reports/r-alice-01/export']:
        assert c.get(path).status_code==401


def test_t01_user_isolation_read_export_and_actions(bank):
    _,client,_=bank;a=client('alice.demo')
    assert a.get('/api/reports/r-alice-01').status_code==200
    for path in ['/api/reports/r-benoit-01','/api/reports/r-benoit-01/export']:
        assert a.get(path).status_code==404
    assert a.post('/api/alerts/a-benoit-01/ack',json={}).status_code==404
    assert 'p-benoit' not in a.get('/api/dashboard').text


def test_t02_soignant_identity_is_not_access(bank):
    _,client,_=bank;c=client('lina.demo');unrelated=client('marc.demo')
    assert c.get('/api/dashboard').json()['reports']==[]
    assert c.get('/api/reports/r-alice-01').status_code==404
    a=client('alice.demo');grant(a)
    assert unrelated.get('/api/reports/r-alice-01').status_code==404
    assert unrelated.get('/api/reports/r-alice-01/export').status_code==404


def test_t03_share_read_revoke_and_export(bank):
    _,client,_=bank;a=client('alice.demo');c=client('lina.demo');sid=grant(a)
    summary=c.get('/api/dashboard').json()['reports'][0]
    assert 'metrics' not in summary
    assert a.get('/api/dashboard').json()['shares'][0]['opened_at'] is None
    assert c.get('/api/reports/r-alice-01').json()['metrics']['episodes']==12
    assert a.get('/api/dashboard').json()['shares'][0]['opened_at'] is not None
    assert c.get('/api/reports/r-alice-01/export').status_code==200
    assert a.post(f'/api/shares/{sid}/revoke',json={}).status_code==200
    assert c.get('/api/dashboard').json()['reports']==[]
    assert c.get('/api/reports/r-alice-01').status_code==404
    assert c.get('/api/reports/r-alice-01/export').status_code==404


@pytest.mark.parametrize('username',['prevention.demo','support.demo','securite.demo'])
def test_t04_t13_non_medical_roles_never_get_health(bank,username):
    _,client,_=bank;c=client(username)
    content=c.get('/api/dashboard')
    for field in ['metrics','reports','thumb_pct','episodes','alerts','shares']:
        assert field not in content.json()
        assert '"'+field+'"' not in content.text
    for path in ['/api/reports/r-alice-01','/api/reports/r-alice-01/export']:
        assert c.get(path).status_code==404
    assert c.post('/api/shares',json={'report_id':'r-alice-01','clinician_id':'c-lina','duration_hours':24}).status_code==404


def test_cannot_claim_role_patient_or_organisation(bank):
    _,client,_=bank;c=client('alice.demo')
    assert c.get('/api/dashboard?role=security&patient_id=p-benoit',headers={'X-Role':'security','X-User-Id':'u-benoit'}).json()['role']=='user'
    assert c.post('/api/accounts/u-benoit/suspend',json={}).status_code==404
    assert c.post('/api/shares',json={'report_id':'r-alice-01','clinician_id':'c-lina','duration_hours':24,'user_id':'u-benoit'}).status_code==422


def test_unrelated_grant_and_other_report_refused(bank):
    _,client,_=bank;c=client('alice.demo')
    for report,doctor in [('r-alice-01','c-marc'),('r-benoit-01','c-lina')]:
        assert c.post('/api/shares',json={'report_id':report,'clinician_id':doctor,'duration_hours':24}).status_code==404


def test_existing_share_needs_current_relation_and_expiry(bank):
    app,client,_=bank;a=client('alice.demo');c=client('lina.demo');sid=grant(a)
    with app.state.factory() as db:
        db.get(CareLink,'link-a').enabled=False;db.commit()
    assert c.get('/api/reports/r-alice-01').status_code==404
    with app.state.factory() as db:
        db.get(CareLink,'link-a').enabled=True;db.get(Share,sid).expires=time.time()-1;db.commit()
    assert c.get('/api/reports/r-alice-01/export').status_code==404


def test_t12_mfa_wrong_then_valid_and_replay(bank):
    _,client,secrets=bank;c=client();cred=secrets['alice.demo']
    body={'username':'alice.demo','password':cred['password'],'otp':pyotp.TOTP(cred['otp_secret']).now()}
    wrong={**body,'otp':str((int(body['otp'])+100000)%1000000).zfill(6)}
    assert c.post('/api/login',json=wrong).status_code==401
    old=c.cookies.get(COOKIE)
    valid=c.post('/api/login',json=body)
    assert valid.status_code==200
    assert old!=c.cookies.get(COOKIE)
    assert 'httponly' in valid.headers['set-cookie'].lower()
    assert 'samesite=strict' in valid.headers['set-cookie'].lower()
    other=client()
    assert other.post('/api/login',json=body).status_code==401


def test_session_logout_and_absolute_expiry(bank):
    app,client,_=bank;c=client('alice.demo')
    token=c.cookies.get(COOKIE)
    assert c.post('/api/logout',json={}).status_code==200
    c.cookies.set(COOKIE,token)
    assert c.get('/api/dashboard').status_code==401
    b=client('benoit.demo')
    with app.state.factory() as db:
        db.get(WebSession,hashed(b.cookies.get(COOKIE))).expires=time.time()-1;db.commit()
    assert b.get('/api/dashboard').status_code==401


def test_idle_timeout(bank):
    app,client,_=bank;c=client('alice.demo')
    with app.state.factory() as db:
        db.get(WebSession,hashed(c.cookies.get(COOKIE))).last_seen=time.time()-901;db.commit()
    assert c.get('/api/dashboard').status_code==401


def test_csrf_origin_and_json_required(bank):
    _,client,_=bank;c=client('alice.demo')
    endpoint='/api/alerts/a-alice-01/ack'
    assert c.post(endpoint,json={},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert c.post(endpoint,json={},headers={'Origin':'https://attacker.invalid'}).status_code==403
    assert c.post(endpoint,content='{}',headers={'Content-Type':'text/plain'}).status_code==415


def test_rate_limit(bank):
    _,client,_=bank;c=client()
    for _ in range(12):
        assert c.post('/api/login',json={'username':'absent','password':'wrong','otp':'123456'}).status_code==401
    assert c.post('/api/login',json={'username':'absent','password':'wrong','otp':'123456'}).status_code==429


def test_admin_suspend_invalidates_existing_sessions(bank):
    _,client,_=bank;a=client('alice.demo');s=client('securite.demo')
    assert s.post('/api/accounts/u-alice/suspend',json={}).status_code==200
    assert a.get('/api/dashboard').status_code==401
    assert s.post('/api/accounts/s-securite/suspend',json={}).status_code==404
    assert s.get('/api/reports/r-alice-01').status_code==404


def test_support_scope_and_no_free_health_text(bank):
    _,client,_=bank;a=client('alice.demo');s=client('support.demo')
    assert a.post('/api/tickets',json={'category':'capteur','symptome':'douleur'}).status_code==422
    ticket=a.post('/api/tickets',json={'category':'capteur'}).json()
    assert s.post(f'/api/tickets/{ticket["id"]}/resolve',json={}).status_code==200
    assert s.post('/api/tickets/t-benoit-01/resolve',json={}).status_code==404
    assert 't-benoit-01' not in s.get('/api/dashboard').text


def test_prevention_is_not_health_aggregation(bank):
    _,client,_=bank;e=client('prevention.demo')
    assert e.post('/api/prevention/pr-a-01/complete',json={}).status_code==200
    assert e.post('/api/prevention/pr-b-01/complete',json={}).status_code==404
    data=e.get('/api/dashboard').json()
    assert set(data)=={'role','user','environment','capabilities','prevention'}


def test_real_marked_report_not_served(bank):
    app,client,_=bank;a=client('alice.demo')
    with app.state.factory() as db:db.get(Report,'r-alice-01').synthetic=False;db.commit()
    assert a.get('/api/reports/r-alice-01').status_code==404
    assert all(r['id']!='r-alice-01' for r in a.get('/api/dashboard').json()['reports'])


def test_null_and_historical_semantics(bank):
    _,client,_=bank;a=client('alice.demo')
    r=a.get('/api/reports/r-alice-02').json()
    assert r['metrics']['thumb_pct'] is None
    assert r['quality']=='invalid' and r['synthetic'] is True
    assert 'figé' in r['notice']


def test_headers_no_cache_secrets_or_inline_code(bank):
    _,client,secrets=bank;s=client('securite.demo');resp=s.get('/api/dashboard')
    assert resp.headers['cache-control']=='no-store'
    assert 'unsafe-inline' not in resp.headers['content-security-policy']
    assert resp.headers['x-frame-options']=='DENY'
    for c in secrets.values():
        assert c['password'] not in resp.text and c['otp_secret'] not in resp.text
    assert s.get('/api/session',headers={'Host':'evil.example'}).status_code==400
    assert s.get('/.runtime/comptes_locaux.json').status_code==404
    assert s.get('/api/openapi.json').status_code==404


def test_payload_size_and_unsupported_actions(bank):
    _,client,_=bank;s=client('securite.demo')
    assert s.post('/api/login',json={'padding':'x'*9000}).status_code==413
    assert s.post('/api/accounts/s-securite/role',json={'role':'clinician'}).status_code==404
    assert s.post('/api/emergency-access',json={}).status_code==404
