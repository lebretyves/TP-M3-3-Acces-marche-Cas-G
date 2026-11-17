"""Authenticated, owner-only receipt visibility for the embedded simulator."""
import time
from uuid import uuid4
from app.domain_models import DomainRecord as R
from app.models import Account
from test_domain import domain_bank


def notice(db, run_id, *, ident=None, owner='u-alice', at=None, synthetic=True, **extra):
    stamp=time.time() if at is None else at
    row=R(id=ident or 'usage-'+uuid4().hex,kind='notification',owner_id=owner,device_id='demo-device-a',
        status='active',created_at=stamp,updated_at=stamp,
        data={'kind':'usage','event_kind':'high_force','origin':'manual','simulation_run':run_id,
              'sequence':3,'title':'Simulation manuelle : appui relatif élevé.','synthetic':synthetic,
              'private_payload':'MUST_NOT_LEAVE_SERVICE','read':False,**extra})
    db.add(row)
    return row.id


def test_receipts_owner_and_run_scoping_and_allowlisted_fields(domain_bank):
    factory,client,_=domain_bank;run=str(uuid4());other=str(uuid4())
    with factory.begin() as db:
        own=notice(db,run)
        notice(db,run,owner='u-benoit')
        notice(db,other)
        notice(db,run,synthetic=False)
        notice(db,run,at=time.time()-86402)
    response=client('u-alice').get('/api/simulation-notifications',params={'run_id':run,'owner_id':'u-benoit'})
    assert response.status_code==200,response.text
    body=response.json()
    assert body['scope']=='own_notifications' and body['run_id']==run and not body['truncated']
    assert len(body['notifications'])==1 and body['notifications'][0]['id']==own
    assert set(body['notifications'][0])=={'id','title','event_kind','origin','created_at','sequence'}
    assert 'MUST_NOT_LEAVE_SERVICE' not in response.text and 'owner_id' not in response.text and 'csrf' not in response.text
    assert len(client('u-benoit').get('/api/simulation-notifications',params={'run_id':run}).json()['notifications'])==1
    assert not client('u-alice').get('/api/simulation-notifications',params={'run_id':str(uuid4())}).json()['notifications']
    with factory() as db:
        assert db.get(R,own).data['read'] is False


def test_receipts_require_authenticated_active_user_and_valid_uuid(domain_bank):
    factory,client,_=domain_bank;url='/api/simulation-notifications?run_id='+str(uuid4())
    assert client('').get(url).status_code==401
    for role in ('c-lina','e-atelier','t-support','s-securite'):
        assert client(role).get(url).status_code==404
    assert client('u-alice').get('/api/simulation-notifications?run_id=not-a-uuid').status_code==422
    with factory.begin() as db:db.get(Account,'u-alice').active=False
    assert client('u-alice').get(url).status_code==401


def test_receipts_disclose_bounded_search_even_if_matching_run_is_outside_limit(domain_bank):
    factory,client,_=domain_bank;run=str(uuid4());other=str(uuid4());now=time.time()
    with factory.begin() as db:
        notice(db,run,at=now-5000)
        for index in range(500):notice(db,other,at=now-index)
    result=client('u-alice').get('/api/simulation-notifications',params={'run_id':run}).json()
    assert result['truncated'] is True and result['notifications']==[]


def test_receipts_ignore_unbound_legacy_or_malformed_event_metadata(domain_bank):
    factory,client,_=domain_bank;run=str(uuid4())
    with factory.begin() as db:
        notice(db,run,sequence=None)
        notice(db,run,sequence=True)
        notice(db,run,event_kind='medical_diagnosis')
        notice(db,run,origin='physical')
    result=client('u-alice').get('/api/simulation-notifications',params={'run_id':run}).json()
    assert not result['notifications']
