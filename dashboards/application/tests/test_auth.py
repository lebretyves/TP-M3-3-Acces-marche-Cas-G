import base64
import time
from types import SimpleNamespace
import jwt
import pyotp
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from app.main import create_app,COOKIE
from app.seed import seed
from app.domain_seed import seed_domain
from app.auth_oidc import Provider
from app.models import Account, WebSession
from sqlalchemy import select


@pytest.fixture
def bank(tmp_path,monkeypatch):
    monkeypatch.setenv('SKELIVIA_AUTH_MODE','local')
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(tmp_path/'data.key'))
    app=create_app('sqlite:///'+(tmp_path/'auth.db').as_posix(),testing=True)
    credentials=seed(app.state.factory)
    with app.state.factory() as db: seed_domain(db);db.commit()
    with TestClient(app,base_url='http://127.0.0.1:8772') as client:
        client.headers['origin']='http://127.0.0.1:8772'
        session=client.get('/api/session').json()
        client.headers['x-csrf-token']=session['csrf_token']
        yield client,credentials,app
    app.state.engine.dispose()


def login(client,credentials,username='alice.demo',counter_offset=-1):
    credential=next(c for c in credentials if c['username']==username)
    code=pyotp.TOTP(credential['otp_secret']).at((int(time.time()//30)+counter_offset)*30)
    response=client.post('/api/login',json={'username':username,'password':credential['password'],'otp':code})
    if response.status_code==200:client.headers['x-csrf-token']=response.json()['csrf_token']
    return response,credential,code


def test_session_rotation_logout_and_new_browser_notification(bank):
    client,credentials,_=bank
    previous=client.cookies.get(COOKIE)
    response,_,_=login(client,credentials)
    assert response.status_code==200
    assert client.cookies.get(COOKIE)!=previous
    workspace=client.get('/api/workspace').json()
    assert any(n['kind']=='security' for n in workspace['notifications'])
    assert client.post('/api/logout',json={}).status_code==200
    assert client.get('/api/workspace').status_code==401


def test_csrf_origin_and_mfa_replay(bank):
    client,credentials,_=bank
    assert client.post('/api/login',json={},headers={'origin':'https://untrusted.example'}).status_code==403
    assert client.post('/api/login',json={},headers={'x-csrf-token':'invalid'}).status_code==403
    response,credential,used=login(client,credentials)
    assert response.status_code==200
    assert client.post('/api/reauth',json={'password':credential['password'],'otp':used}).status_code==401
    current=pyotp.TOTP(credential['otp_secret']).now()
    assert client.post('/api/reauth',json={'password':credential['password'],'otp':current}).status_code==200


def test_local_rate_limit(bank):
    client,_,_=bank
    statuses=[client.post('/api/login',json={'username':'unknown','password':'invalid','otp':'000000'}).status_code for _ in range(13)]
    assert statuses[-1]==429


def test_simulator_entry_does_not_open_cross_site_api_access(bank):
    client,_,_=bank
    navigation={'sec-fetch-site':'cross-site','sec-fetch-mode':'navigate','sec-fetch-dest':'document'}
    assert client.get('/api/session',headers=navigation).status_code==403
    assert client.get('/api/workspace',headers=navigation).status_code==403
    assert client.get('/static/app.js',headers=navigation).status_code==403
    assert client.get('/static/simulation.html',headers=navigation).status_code==200
    assert client.get('/static/simulation.html',headers={'sec-fetch-site':'cross-site'}).status_code==403
    assert client.post('/api/actions',json={'action':'access.check','payload':{}},headers=navigation).status_code==403


def test_only_simulation_launcher_allows_same_origin_framing(bank):
    client,_,_=bank
    response=client.get('/static/simulation.html',headers={'sec-fetch-site':'same-origin','sec-fetch-mode':'navigate','sec-fetch-dest':'iframe'})
    assert response.status_code==200
    assert response.headers['x-frame-options']=='SAMEORIGIN'
    assert "frame-ancestors 'self'" in response.headers['content-security-policy']
    assert len(response.headers.get_list('x-frame-options'))==1
    for path in ['/','/api/session','/static/app.js']:
        response=client.get(path)
        assert response.headers['x-frame-options']=='DENY'
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    blocked=client.get('/static/simulation.html',headers={'sec-fetch-site':'cross-site','sec-fetch-mode':'navigate','sec-fetch-dest':'iframe'})
    assert blocked.status_code==403


@pytest.mark.parametrize('cause',['absolute_expiry','inactivity','suspended_account'])
def test_existing_session_cannot_survive_expiry_or_suspension(bank,cause):
    client,credentials,app=bank
    assert login(client,credentials)[0].status_code==200
    with app.state.factory() as db:
        session=db.scalar(select(WebSession).where(WebSession.user_id=='u-alice'))
        if cause=='absolute_expiry':session.expires=time.time()-1
        elif cause=='inactivity':session.last_seen=time.time()-901
        else:db.get(Account,'u-alice').active=False
        db.commit()
    assert client.get('/api/workspace').status_code==401


@pytest.fixture
def oidc(monkeypatch,tmp_path):
    monkeypatch.setenv('SKELIVIA_OIDC_ISSUER','https://identity.example/realms/test')
    monkeypatch.setenv('SKELIVIA_OIDC_CLIENT_SECRET_FILE',str(tmp_path/'client.secret'))
    provider=Provider()
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    jwk=jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(),as_dict=True)
    jwk.update(kid='test',alg='RS256',use='sig')
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url):return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'keys':[jwk]})
    monkeypatch.setattr(provider,'client',Client)
    now=int(time.time())
    claims={'iss':provider.issuer,'aud':provider.client_id,'sub':'subject','iat':now,'exp':now+60,'nonce':'bound-nonce','auth_time':now,'acr':'2'}
    encode=lambda values:jwt.encode(values,key,algorithm='RS256',headers={'kid':'test'})
    return provider,claims,encode,{'jwks_uri':provider.issuer+'/certs'}


def test_oidc_verified_claims_and_pinned_endpoints(oidc):
    provider,claims,encode,metadata=oidc
    assert provider.verify(encode(claims),metadata,nonce='bound-nonce')['sub']=='subject'
    with pytest.raises(ValueError):provider.local_endpoint('https://untrusted.example/jwks')


@pytest.mark.parametrize('override',[{'nonce':'other'},{'aud':'other'},{'iss':'https://other.example'},{'acr':'1'},{'auth_time':0},{'exp':1}])
def test_oidc_rejects_untrusted_or_stale_identity(oidc,override):
    provider,claims,encode,metadata=oidc
    with pytest.raises((ValueError,jwt.PyJWTError)):
        provider.verify(encode({**claims,**override}),metadata,nonce='bound-nonce')


def test_logout_token_is_not_an_id_token(oidc):
    provider,claims,encode,metadata=oidc
    logout={k:v for k,v in claims.items() if k not in {'nonce','auth_time','acr'}}
    logout.update(jti='logout-unique',events={'http://schemas.openid.net/event/backchannel-logout':{}})
    assert provider.verify(encode(logout),metadata,logout=True)['jti']=='logout-unique'
    with pytest.raises(ValueError):provider.verify(encode({**logout,'nonce':'not-allowed'}),metadata,logout=True)
