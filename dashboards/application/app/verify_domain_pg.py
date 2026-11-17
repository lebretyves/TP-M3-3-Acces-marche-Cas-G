"""Non-owner PostgreSQL integration probes; all QA mutations are rolled back.

Run in the app service identity: python -m app.verify_domain_pg.
Never prints URLs, credentials, encrypted content or medical payloads.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from .database import runtime_url, register_models, configure_actor
from .models import Account, Report
from .domain_models import DomainRecord as R, DomainJob as J, DomainGrant as G, DomainDiagnostic as D
from .domain import workspace, dispatch, SCHEMAS, diagnostic


def main():
    register_models()
    engine=create_engine(runtime_url(),hide_parameters=True)
    if engine.dialect.name!='postgresql':raise RuntimeError('PostgreSQL verification requires PostgreSQL.')
    factory=sessionmaker(engine,expire_on_commit=False)
    with engine.connect() as conn:
        identity=conn.execute(text("SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")).one()
        owners=conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tableowner=current_user")).scalars().all()
        if identity[0]!='skelivia_app' or identity[1] or identity[2] or owners:
            raise RuntimeError('Verification must run as non-owner skelivia_app without BYPASSRLS.')
    results=[]
    prefix='qa-'+uuid.uuid4().hex[:12]
    fresh=SimpleNamespace(authenticated_at=time.time())
    stage={'name':'initialization'}

    def actor(db,actor_id):
        db.flush();db.expunge_all()
        a=db.get(Account,actor_id)
        assert a is not None,'Missing seeded actor'
        configure_actor(db,a)
        return a

    def command(db,a,name,**payload):
        stage['name']=name
        parsed=SCHEMAS[name].model_validate(payload).model_dump()
        result=dispatch(db,a,name,parsed,fresh);db.flush();return result

    def check(name,fn):
        stage['name']=name
        with factory() as db:
            try:
                fn(db)
                results.append({'test':name,'status':'PASS'})
            except Exception as exc:
                error={'test':name,'status':'FAIL','error':type(exc).__name__,'stage':stage['name']}
                if isinstance(exc,HTTPException):error['http_status']=exc.status_code
                original=getattr(exc,'orig',None)
                state=getattr(original,'sqlstate',None)
                if state:error['sqlstate']=state
                results.append(error)
            finally:
                db.rollback()

    def ws(db,who):
        a=actor(db,who);data=workspace(db,a)
        assert data['role']==a.role
        if a.role in {'employer','support','security'}:
            assert 'measures' not in data and 'documents' not in data
            assert db.scalars(select(Report)).all()==[]
            assert db.scalars(select(R).where(R.kind=='document')).all()==[]
        if a.role=='user':assert all(x['patient_id']==a.patient_id for x in data['measures'])
    for who in ['u-alice','u-benoit','c-lina','c-marc','e-atelier','t-support','s-securite','s-approbateur']:
        check('workspace-'+who,lambda db,who=who:ws(db,who))

    def sharing(db):
        a=actor(db,'u-alice');day=datetime.now(timezone.utc).date().isoformat()
        sid=command(db,a,'share.create',clinician_id='c-lina',start=day,end=day,categories=['contact'],duration_hours=1)['id']
        c=actor(db,'c-lina');data=workspace(db,c)
        assert data['measures'] and all(set(m['metrics'])<={'contact_seconds'} for m in data['measures'])
        command(db,c,'document.publish',patient_id='p-alice',kind='report',title=prefix,body='QA rollback document')
        a=actor(db,'u-alice');assert any(d['title']==prefix for d in workspace(db,a)['documents'])
        other=actor(db,'c-marc');assert not any(d['title']==prefix for d in workspace(db,other)['documents'])
        a=actor(db,'u-alice');command(db,a,'share.revoke',id=sid)
        c=actor(db,'c-lina')
        other_grant=db.scalar(select(G.id).where(G.patient_id=='p-alice',G.clinician_id==c.id,G.active.is_(True),G.expires>time.time()))
        if not other_grant:assert not any(d['title']==prefix for d in workspace(db,c)['documents'])
    check('grant-documents-categories-revocation',sharing)

    def notification(db):
        c=actor(db,'c-lina')
        result=command(db,c,'recommendation.publish',org_id='atelier-a',title=prefix,body='QA organisation only',category='organisation')
        e=actor(db,'e-atelier');data=workspace(db,e)
        assert any(r['id']==result['id'] for r in data['recommendations'])
        assert any(n['kind']=='recommendation' for n in data['notifications'])
        command(db,e,'recommendation.status',id=result['id'],status='done')
        c=actor(db,'c-lina');assert next(r for r in workspace(db,c)['recommendations'] if r['id']==result['id'])['status']=='done'
    check('organisation-and-cross-owner-notification',notification)

    def support(db):
        s=actor(db,'t-support');j=command(db,s,'diagnostic.request',id='ticket-alice',duration_minutes=5,reason='QA temporary diagnosis')['id']
        a=actor(db,'u-alice');command(db,a,'diagnostic.approve',id=j)
        s=actor(db,'t-support');assert diagnostic(db.get(R,'ticket-alice'))
        assert any(d['id']=='demo-device-a' for d in workspace(db,s)['devices'])
        command(db,s,'device.calibrate',device_id='demo-device-a',ticket_id='ticket-alice')
        command(db,s,'diagnostic.revoke',id='ticket-alice')
        db.expunge_all();assert db.get(R,'demo-device-a') is None
        assert db.get(R,'ticket-benoit') is None
    check('support-jobs-diagnostic-expiry-scope',support)

    def scope_route(db):
        c=actor(db,'c-lina');r=command(db,c,'ticket.create',title=prefix,body='QA software only',category='software')
        s=actor(db,'t-support');t=db.get(R,r['id']);assert t and t.device_id is None
        command(db,s,'ticket.reply',id=t.id,body='QA technical reply')
        c=actor(db,'c-lina');assert any(n['kind']=='support' for n in workspace(db,c)['notifications'])
    check('clinician-software-ticket-routing',scope_route)

    def reminder(db):
        c=actor(db,'c-lina');r=command(db,c,'reminder.create',patient_id='p-alice',due=datetime.now(timezone.utc).date().isoformat(),body=prefix)
        command(db,c,'reminder.delete',id=r['id']);assert not any(x['id']==r['id'] for x in workspace(db,c)['reminders'])
    check('reminder-soft-delete',reminder)

    def approve(db):
        s=actor(db,'s-securite')
        qa=Account(id=prefix,username=prefix,name='QA rollback account',role='user',org_id='qa',patient_id=None,password_hash='disabled-qa',otp_secret='DISABLED',active=False)
        db.add(qa);db.flush()
        r=command(db,s,'account.request',target_id=prefix,operation='reactivate',reason='QA dual approval')
        try:command(db,s,'account.approve',id=r['id'])
        except HTTPException as exc:assert exc.status_code==403
        else:raise AssertionError('Self approval accepted')
        approver=actor(db,'s-approbateur');command(db,approver,'account.approve',id=r['id'])
        assert db.get(Account,prefix).active
    check('distinct-account-approver',approve)

    def raw_crypto(db):
        a=actor(db,'u-alice');command(db,a,'settings.save',large_text=True)
        raw=db.execute(text("SELECT data FROM domain_records WHERE kind='settings' AND owner_id=:owner"),{'owner':a.id}).scalars().all()
        assert raw and all(v.startswith('v1:') and 'large_text' not in v for v in raw)
    check('encrypted-sensitive-column',raw_crypto)

    engine.dispose()
    print(json.dumps({'identity':'non-owner skelivia_app','mutations':'rolled back','results':results},ensure_ascii=False,indent=2))
    if any(r['status']=='FAIL' for r in results):raise SystemExit(1)


if __name__=='__main__':main()
