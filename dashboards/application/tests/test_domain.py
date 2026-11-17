"""Domain authorization tests use real persistence and a test-only actor dependency."""
import time
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, Request, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.database import database
from app.domain import install_domain
from app.domain_models import DomainRecord as R, DomainJob as J, DomainGrant as G, SupportScope
from app.domain_seed import seed_domain
from app.models import Account, CareLink, WebSession
from app.models import Report
from app.domain import export_measure_rows
from app.domain import device_json
from datetime import datetime,timezone
from app.seed import seed


@pytest.fixture
def domain_bank(tmp_path,monkeypatch):
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(tmp_path/'key'))
    engine,factory=database('sqlite:///'+(tmp_path/'domain.db').as_posix())
    seed(factory)
    with factory() as db:
        if not db.get(Account,'s-approbateur'):
            original=db.get(Account,'s-securite')
            db.add(Account(id='s-approbateur',username='approbateur.test',name='Approver',role='security',org_id='interne',password_hash=original.password_hash,otp_secret=original.otp_secret))
        seed_domain(db);db.commit()
    app=FastAPI()
    def actor(request:Request):
        with factory() as db:
            a=db.get(Account,request.headers.get('x-test-actor',''))
            if not a or not a.active:raise HTTPException(401)
            return a
    def csrf(request:Request):
        if request.headers.get('x-test-csrf')!='valid':raise HTTPException(403)
        return SimpleNamespace(authenticated_at=time.time() if request.headers.get('x-test-stepup')=='yes' else 0)
    install_domain(app,factory,actor,csrf)
    clients=[]
    def client(who,stepup=True):
        c=TestClient(app);c.headers.update({'x-test-actor':who,'x-test-csrf':'valid','x-test-stepup':'yes' if stepup else 'no'});clients.append(c);return c
    yield factory,client,engine
    for c in clients:c.close()
    engine.dispose()


def act(c,action,**payload):return c.post('/api/actions',json={'action':action,'payload':payload})
def grant(c,categories=None):
    today=time.strftime('%Y-%m-%d',time.gmtime())
    response=act(c,'share.create',clinician_id='c-lina',start=today,end=today,categories=categories or ['contact','pressure','moves'],duration_hours=24)
    assert response.status_code==200,response.text
    return response.json()['id']


def test_owner_and_role_isolation_and_export(domain_bank):
    _,client,_=domain_bank
    alice=client('u-alice');benoit=client('u-benoit')
    assert all(x['patient_id']=='p-alice' for x in alice.get('/api/workspace').json()['measures'])
    assert all(x['patient_id']=='p-benoit' for x in benoit.get('/api/workspace').json()['measures'])
    for user in ['e-atelier','t-support','s-securite']:
        result=client(user).get('/api/workspace').json()
        assert 'documents' not in result and 'measures' not in result
    assert client('c-lina').get('/api/export?kind=personal&start=2026-01-01&end=2026-12-31').status_code==404
    assert act(alice,'ticket.reply',id='ticket-benoit',body='Not mine').status_code==404


def test_grant_categories_relation_expiry_and_revoke(domain_bank):
    factory,client,_=domain_bank;a=client('u-alice');c=client('c-lina');other=client('c-marc')
    assert c.get('/api/workspace').json()['measures']==[]
    sid=grant(a,['contact'])
    result=c.get('/api/workspace').json()
    assert result['measures'] and set(result['measures'][0]['metrics'])=={'contact_seconds'}
    assert all(r['patient_id']!='p-alice' for r in other.get('/api/workspace').json()['measures'])
    with factory() as db:db.get(CareLink,'link-a').enabled=False;db.commit()
    assert c.get('/api/workspace').json()['documents']==[]
    with factory() as db:db.get(CareLink,'link-a').enabled=True;db.get(G,sid).expires=time.time()-1;db.commit()
    assert c.get('/api/workspace').json()['measures']==[]
    with factory() as db:db.get(G,sid).expires=time.time()+3600;db.commit()
    assert act(a,'share.revoke',id=sid).status_code==200
    assert c.get('/api/workspace').json()['documents']==[]


def test_grant_date_excludes_outside_and_no_role_claim(domain_bank):
    _,client,_=domain_bank;a=client('u-alice');c=client('c-lina')
    assert act(a,'share.create',clinician_id='c-marc',start='2026-01-01',end='2026-01-02',categories=['contact'],duration_hours=24).status_code==404
    response=act(a,'share.create',clinician_id='c-lina',start='2000-01-01',end='2000-01-02',categories=['contact'],duration_hours=24)
    assert response.status_code==200
    assert c.get('/api/workspace').json()['measures']==[]
    assert act(a,'share.revoke',id=response.json()['id'],role='security').status_code==422
    assert a.get('/api/workspace?role=security').json()['role']=='user'


def test_versions_persist_and_cannot_overwrite_other_patient(domain_bank):
    factory,client,_=domain_bank;a=client('u-alice');c=client('c-lina');grant(a)
    p={'patient_id':'p-alice','kind':'report','title':'Bilan','body':'Version initiale privée'}
    first=act(c,'document.publish',**p);assert first.status_code==200
    docs=a.get('/api/workspace').json()['documents'];doc=next(d for d in docs if d['id']==first.json()['id'])
    second=act(c,'document.publish',**{**p,'body':'Version corrigée','document_id':doc['document_id']});assert second.status_code==200
    assert act(c,'document.publish',**{**p,'patient_id':'p-benoit','document_id':doc['document_id']}).status_code==404
    with factory() as db:
        versions=list(db.scalars(select(R).where(R.document_id==doc['document_id']).order_by(R.version)))
        assert [v.version for v in versions]==[1,2]
        assert versions[0].data['body']=='Version initiale privée'
        raw=db.execute(text('select data from domain_records where id=:id'),{'id':first.json()['id']}).scalar()
        assert raw.startswith('v1:') and 'privée' not in raw


def test_employer_org_status_and_no_refused_fields(domain_bank):
    _,client,_=domain_bank;c=client('e-atelier')
    rows=c.get('/api/workspace').json()['recommendations']
    assert all('patient_id' not in r for r in rows)
    assert act(c,'recommendation.status',id='rec-atelier-b',status='done').status_code==404
    assert act(c,'recommendation.status',id='rec-atelier-a',status='blocked',reason='refused feature').status_code==422
    assert act(c,'recommendation.status',id='rec-atelier-a',status='blocked').status_code==200
    assert c.get('/api/workspace').json()['recommendations'][0]['history'][-1]['status']=='blocked'


def test_support_assignment_and_diagnostic_owner_approval(domain_bank):
    factory,client,_=domain_bank;t=client('t-support');a=client('u-alice');b=client('u-benoit')
    assert act(t,'ticket.reply',id='ticket-benoit',body='cross organisation').status_code==404
    assert act(t,'device.calibrate',device_id='demo-device-a',ticket_id='ticket-alice').status_code==409
    request=act(t,'diagnostic.request',id='ticket-alice',duration_minutes=15,reason='Connexion à examiner');assert request.status_code==200
    job=request.json()['id']
    assert act(b,'diagnostic.approve',id=job).status_code==404
    assert act(a,'diagnostic.approve',id=job).status_code==200
    assert act(t,'device.calibrate',device_id='demo-device-a',ticket_id='ticket-alice').status_code==200
    assert act(t,'ticket.checks',id='ticket-alice',connection=True,sensors=True,calibration=True).status_code==200
    assert act(t,'ticket.status',id='ticket-alice',status='resolved').status_code==409
    assert act(t,'diagnostic.revoke',id='ticket-alice').status_code==200
    state=t.get('/api/workspace').json();assert state['devices']==[]
    assert all(not x['diagnostic_active'] for x in state['tickets'])
    with factory() as db:
        job=db.scalar(select(J).where(J.kind=='calibration'));assert job.status=='pending' and job.result=={}


def test_clinician_ticket_never_controls_patient_device(domain_bank):
    factory,client,_=domain_bank;c=client('c-lina')
    assert act(c,'ticket.create',title='Logiciel',body='Problème interface',category='software',device_id='demo-device-a').status_code==404
    r=act(c,'ticket.create',title='Logiciel',body='Problème interface',category='software');assert r.status_code==200
    ticket=next(t for t in c.get('/api/workspace').json()['tickets'] if t['id']==r.json()['id']);assert ticket['device_id'] is None
    assert ticket['assigned_to']=='t-support'
    support=client('t-support')
    assert act(support,'ticket.reply',id=ticket['id'],body='Réponse logicielle').status_code==200
    with factory() as db:db.get(SupportScope,('t-support','soins-a')).active=False;db.commit()
    assert act(support,'ticket.reply',id=ticket['id'],body='Accès retiré').status_code==404
    assert all(t['id']!=ticket['id'] for t in support.get('/api/workspace').json()['tickets'])


def test_sessions_targeted_metadata_and_invalidation(domain_bank):
    factory,client,_=domain_bank
    with factory() as db:
        db.add_all([WebSession(token_hash='a'*64,user_id='u-alice',csrf='secret-a',expires=time.time()+600,last_seen=time.time(),authenticated_at=time.time()),WebSession(token_hash='b'*64,user_id='u-benoit',csrf='secret-b',expires=time.time()+600,last_seen=time.time(),authenticated_at=time.time())]);db.commit()
    a=client('u-alice');s=client('s-securite')
    public=a.get('/api/workspace').json()['sessions'];assert len(public)==1
    assert public[0]['id']!='a'*64 and 'secret-a' not in str(public)
    others=s.get('/api/workspace').json()['sessions'];other=next(x for x in others if x['account_id']=='u-benoit')
    assert act(a,'session.revoke',id=other['id'],reason='cross account').status_code==404
    assert act(client('s-securite',False),'session.revoke',id=other['id'],reason='investigation').status_code==403
    assert act(s,'session.revoke',id=other['id'],reason='investigation').status_code==200
    with factory() as db:assert db.get(WebSession,'b'*64) is None


def test_security_account_approval_distinct_and_reauthentication(domain_bank):
    factory,client,_=domain_bank;s=client('s-securite');approver=client('s-approbateur')
    body={'target_id':'u-alice','operation':'suspend','reason':'Contrôle de sécurité'}
    assert act(client('s-securite',False),'account.request',**body).status_code==403
    request=act(s,'account.request',**body);assert request.status_code==200;rid=request.json()['id']
    assert act(s,'account.approve',id=rid).status_code==403
    assert act(approver,'account.approve',id=rid).status_code==200
    with factory() as db:assert db.get(Account,'u-alice').active is False
    assert act(approver,'account.approve',id=rid).status_code==409
    assert act(s,'account.request',target_id='s-securite',operation='role',role='clinician',reason='self').status_code==404


def test_creation_and_deletion_are_pending_jobs_not_fake_success(domain_bank):
    factory,client,_=domain_bank;s=client('s-securite');ap=client('s-approbateur');a=client('u-alice')
    r=act(s,'account.request',operation='create',username='new.test',name='New',role='user',org_id='atelier-a',reason='Onboarding')
    assert r.status_code==200
    assert act(ap,'account.approve',id=r.json()['id']).status_code==200
    deletion=act(a,'deletion.request',reason='Supprimer mon compte');assert deletion.status_code==200
    assert act(s,'deletion.review',id=deletion.json()['id'],reason='Conservation à examiner').status_code==200
    with factory() as db:
        assert db.scalar(select(Account).where(Account.username=='new.test')) is None
        assert db.get(Account,'u-alice').active
        assert db.get(R,deletion.json()['id']).status=='pending'
        assert {j.kind for j in db.scalars(select(J))}=={'deletion','account_provision'}


def test_incident_requires_qualification_action_and_proof(domain_bank):
    _,client,_=domain_bank;s=client('s-securite')
    assert act(s,'incident.close',id='incident-demo',proof='Retour vérifié').status_code==409
    assert act(s,'incident.qualify',id='incident-demo',status='confirmed',reason='Éléments techniques').status_code==200
    assert act(s,'incident.close',id='incident-demo',proof='Retour vérifié').status_code==409
    assert act(s,'incident.action',id='incident-demo',body='Règle corrigée').status_code==200
    assert act(s,'incident.close',id='incident-demo',proof='Journaux vérifiés').status_code==200
    assert act(s,'incident.action',id='incident-demo',body='Modification après clôture').status_code==409


def test_preferences_owner_csrf_and_unsupported_actions(domain_bank):
    _,client,_=domain_bank;a=client('u-alice');b=client('u-benoit')
    assert act(a,'settings.save',large_text=True,pause_minutes=30).status_code==200
    assert a.get('/api/workspace').json()['settings']['large_text']
    assert not b.get('/api/workspace').json()['settings']['large_text']
    assert act(client('e-atelier'),'settings.save',channels={'pause':'both'}).status_code==404
    assert act(a,'questionnaire.create',body='refused').status_code==422
    assert a.post('/api/actions',json={'action':'pause.snooze','payload':{'minutes':10}},headers={'x-test-csrf':'wrong'}).status_code==403


def test_date_filter_precedes_limit_pagination_and_explicit_export_cap(domain_bank):
    factory,client,_=domain_bank
    with factory() as db:
        for index in range(1005):
            db.add(Report(id=f'qa-recent-{index:04}',patient_id='p-alice',title='QA',recorded_at='2026-10-20T12:00:00+00:00',quality='valid',metrics={'contact_seconds':1},synthetic=True))
        db.add(Report(id='qa-ancient',patient_id='p-alice',title='QA old period',recorded_at='2020-01-10T12:00:00+00:00',quality='valid',metrics={'contact_seconds':2},synthetic=True));db.commit()
    a=client('u-alice')
    old=a.get('/api/export?kind=personal&start=2020-01-01&end=2020-01-31')
    assert old.status_code==200 and [r['id'] for r in old.json()['measures']]==['qa-ancient']
    first=a.get('/api/measures?start=2026-10-01&end=2026-10-31&limit=1000').json()
    assert len(first['measures'])==1000 and first['has_more'] and first['next_cursor']
    second=a.get('/api/measures',params={'start':'2026-10-01','end':'2026-10-31','cursor':first['next_cursor']}).json()
    assert len(second['measures'])==5 and not second['has_more']
    assert not {r['id'] for r in first['measures']} & {r['id'] for r in second['measures']}
    assert client('u-benoit').get('/api/measures',params={'start':'2026-10-01','end':'2026-10-31','cursor':first['next_cursor']}).status_code==422
    with factory() as db:
        with pytest.raises(HTTPException) as error:export_measure_rows(db,db.get(Account,'u-alice'),'2026-10-01','2026-10-31',cap=1000)
        assert error.value.status_code==413
    assert a.get('/api/export?kind=personal&start=2020-01-01&end=2026-11-14').status_code==422
    assert client('e-atelier').get('/api/measures?start=2026-10-01&end=2026-10-31').status_code==404


def test_device_freshness_and_quality_are_not_permanent_connection_claims(domain_bank,monkeypatch):
    factory,_,_=domain_bank;now=1800000000.0;monkeypatch.setattr('app.domain.time.time',lambda:now)
    with factory() as db:
        d=db.get(R,'demo-device-a')
        d.data={**d.data,'connection':'connected','last_quality':'valid','calibration_status':'verified','last_seen':datetime.fromtimestamp(now-121,timezone.utc).isoformat()}
        assert device_json(d)['connection']=='stale' and not device_json(d)['usable']
        d.data={**d.data,'last_seen':datetime.fromtimestamp(now-5,timezone.utc).isoformat(),'last_quality':'invalid'}
        assert device_json(d)['connection']=='connected' and not device_json(d)['usable']
        d.data={**d.data,'last_quality':'valid'};assert device_json(d)['usable']
        d.data={**d.data,'last_seen':None};assert device_json(d)['connection']=='unknown'
        d.data={**d.data,'connection':'retired'};assert device_json(d)['connection']=='retired'
