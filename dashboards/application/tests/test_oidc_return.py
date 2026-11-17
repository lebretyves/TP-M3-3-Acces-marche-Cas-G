"""OIDC return routing stays bound to the existing one-use browser-bound flow."""
import base64
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.auth_oidc import Provider
from app.main import create_app
from app.models import OIDCIdentity, OIDCState
from app.seed import seed


@pytest.fixture
def oidc_bank(tmp_path,monkeypatch):
    # Substitute only the persistence factory in this isolated route test. The
    # deployed OIDC/PostgreSQL requirement remains untouched in database.py.
    from app.database import database
    with monkeypatch.context() as local:
        local.setenv('SKELIVIA_AUTH_MODE','local')
        persistence=database('sqlite:///'+(tmp_path/'return.db').as_posix())
    monkeypatch.setattr('app.main.database',lambda url=None:persistence)
    monkeypatch.setenv('SKELIVIA_AUTH_MODE','oidc')
    monkeypatch.setenv('SKELIVIA_PUBLIC_ORIGIN','https://localhost:8443')
    monkeypatch.setenv('SKELIVIA_OIDC_ISSUER','https://identity.example/realms/test')
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(tmp_path/'data.key'))
    (tmp_path/'data.key').write_bytes(base64.b64encode(b't'*32))
    secret=tmp_path/'test.secret';secret.write_text('isolated-test-only')
    monkeypatch.setenv('SKELIVIA_OIDC_CLIENT_SECRET_FILE',str(secret))
    metadata={'issuer':'https://identity.example/realms/test',
              'authorization_endpoint':'https://identity.example/realms/test/auth',
              'token_endpoint':'https://identity.example/realms/test/token'}
    exchanges=[]
    class Exchange:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def post(self,url,**kwargs):
            exchanges.append(kwargs)
            return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'id_token':'isolated-token'})
    monkeypatch.setattr(Provider,'discovery',lambda self:metadata)
    monkeypatch.setattr(Provider,'client',lambda self:Exchange())
    monkeypatch.setattr(Provider,'verify',lambda self,token,metadata,nonce=None:{'sub':'test-subject','auth_time':time.time(),'sid':'test-sid'})
    app=create_app('sqlite:///'+(tmp_path/'return.db').as_posix(),testing=True)
    seed(app.state.factory)
    with app.state.factory.begin() as db:
        db.add(OIDCIdentity(subject='test-subject',user_id='u-alice'))
    with TestClient(app,base_url='https://localhost:8443',follow_redirects=False) as client:
        yield client,app,exchanges
    app.state.engine.dispose()


def begin(client,target='/'):
    response=client.get('/oidc/login',params={'return_to':target})
    assert response.status_code==302
    query=parse_qs(urlparse(response.headers['location']).query)
    assert query['max_age']==['0']
    assert query['code_challenge_method']==['S256']
    assert query['acr_values']==['2']
    return query['state'][0]


@pytest.mark.parametrize('target',['/','/simulateur/'])
def test_return_target_is_fixed_at_login_and_state_is_consumed(oidc_bank,target):
    client,app,exchanges=oidc_bank
    state=begin(client,target)
    response=client.get('/oidc/callback',params={'state':state,'code':'test-code','return_to':'https://untrusted.example/'})
    assert response.status_code==303
    assert response.headers['location']==target
    assert client.get('/api/session').json()['authenticated']
    assert len(exchanges)==1
    assert client.get('/oidc/callback',params={'state':state,'code':'test-code'}).status_code==400
    assert len(exchanges)==1


@pytest.mark.parametrize('target',['https://untrusted.example/','//untrusted.example/','/\\untrusted.example','/simulateur/../','/simulateur/?next=other','/api/actions','/static/simulation.html'])
def test_rejects_nonallowlisted_return_before_identity_exchange(oidc_bank,target):
    client,_,exchanges=oidc_bank
    assert client.get('/oidc/login',params={'return_to':target}).status_code==400
    assert not exchanges


def test_duplicate_return_query_is_not_ambiguous(oidc_bank):
    client,_,_=oidc_bank
    assert client.get('/oidc/login?return_to=/&return_to=/simulateur/').status_code==400


def test_return_prefix_cannot_be_swapped_and_browser_binding_is_required(oidc_bank):
    client,app,exchanges=oidc_bank
    state=begin(client,'/simulateur/')
    swapped='default.'+state.split('.',1)[1]
    assert client.get('/oidc/callback',params={'state':swapped,'code':'test-code'}).status_code==400
    with TestClient(app,base_url='https://localhost:8443',follow_redirects=False) as other:
        assert other.get('/oidc/callback',params={'state':state,'code':'test-code'}).status_code==400
    assert not exchanges
    assert client.get('/oidc/callback',params={'state':state,'code':'test-code'}).headers['location']=='/simulateur/'


def test_expired_state_does_not_redirect_or_exchange(oidc_bank):
    from app.auth_oidc import digest
    client,app,exchanges=oidc_bank
    state=begin(client,'/simulateur/')
    with app.state.factory.begin() as db:
        db.get(OIDCState,digest(state)).expires=time.time()-1
    assert client.get('/oidc/callback',params={'state':state,'code':'test-code'}).status_code==400
    assert not exchanges
