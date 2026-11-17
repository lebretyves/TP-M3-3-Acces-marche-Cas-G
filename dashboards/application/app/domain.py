"""Domain service: bounded commands, persistent records and object-level authorization."""
from datetime import date, datetime, timezone, timedelta
import base64
import hmac
import json
from hashlib import sha256
import time
import uuid
from typing import Annotated, Literal
from fastapi import Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, create_model
from sqlalchemy import delete, select, and_, or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import object_session
from .models import Account, CareLink, Report, WebSession
from .domain_models import DomainRecord as R, DomainJob as J, DomainGrant as G, DomainDiagnostic as D, SupportScope

Ident=Annotated[str,StringConstraints(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_.:@-]+$')]
Title=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=160)]
Text=Annotated[str,StringConstraints(strip_whitespace=True,min_length=1,max_length=2000)]
Role=Literal['user','clinician','employer','support','security']
Category=Literal['contact','pressure','moves']
Clock=Annotated[str,StringConstraints(pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9]$')]


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)


class Channels(Strict):
    pause: Literal['none','phone','watch','both']='none'
    advice: Literal['none','phone','watch','both']='none'
    report: Literal['none','phone','watch','both']='none'
    support: Literal['none','phone','watch','both']='none'
    calibration: Literal['none','phone','watch','both']='none'


class Envelope(Strict):
    action: Annotated[str,StringConstraints(max_length=60)]
    payload: dict=Field(default_factory=dict)


def schema(schema_name, **fields):
    return create_model(schema_name.replace('.','_'),__base__=Strict,**fields)


def req(t):return (t,...)
def opt(t,default=None):return (t|None,default)
def integer(low,high):return Annotated[int,Field(ge=low,le=high)]


SCHEMAS={
 'settings.save':schema('settings',large_text=opt(bool),high_contrast=opt(bool),pause_enabled=opt(bool),pause_minutes=opt(integer(5,180)),channels=opt(Channels),quiet_start=opt(Clock),quiet_end=opt(Clock)),
 'notification.read':schema('read',id=req(Ident)),
 'pause.snooze':schema('snooze',minutes=req(integer(1,120))),
 'share.create':schema('share',clinician_id=req(Ident),start=req(str),end=req(str),categories=req(Annotated[list[Category],Field(min_length=1,max_length=3)]),duration_hours=req(integer(1,2160))),
 'share.revoke':schema('revoke_share',id=req(Ident)),
 'document.publish':schema('document',patient_id=req(Ident),kind=req(Literal['advice','report']),title=req(Title),body=req(Text),document_id=opt(Ident)),
 'reminder.create':schema('reminder',patient_id=req(Ident),due=req(str),body=req(Text)),
 'reminder.delete':schema('delete_reminder',id=req(Ident)),
 'recommendation.publish':schema('recommendation',org_id=req(Ident),title=req(Title),body=req(Text),category=req(Literal['equipment','layout','organisation'])),
 'recommendation.revise':schema('recommendation_revise',id=req(Ident),title=req(Title),body=req(Text),category=req(Literal['equipment','layout','organisation'])),
 'recommendation.status':schema('recommendation_status',id=req(Ident),status=req(Literal['todo','in_progress','done','blocked'])),
 'ticket.create':schema('ticket',title=req(Title),body=req(Text),category=req(Literal['connection','calibration','replacement','loss','software']),device_id=opt(Ident)),
 'ticket.reply':schema('reply',id=req(Ident),body=req(Text)),
 'ticket.status':schema('ticket_status',id=req(Ident),status=req(Literal['in_progress','waiting','resolved'])),
 'ticket.checks':schema('checks',id=req(Ident),connection=req(bool),sensors=req(bool),calibration=req(bool)),
 'diagnostic.revoke':schema('diag_revoke',id=req(Ident)),
 'diagnostic.request':schema('diag_request',id=req(Ident),duration_minutes=req(integer(1,60)),reason=req(Text)),
 'diagnostic.approve':schema('diag_approve',id=req(Ident)),
 'device.calibrate':schema('calibrate',device_id=req(Ident),ticket_id=opt(Ident)),
 'device.replace':schema('replace',ticket_id=req(Ident),new_device_id=req(Ident)),
 'device.update':schema('update',ticket_id=req(Ident),patch_id=req(Ident)),
 'security.report':schema('security_report',body=req(Text),ticket_id=opt(Ident)),
 'incident.qualify':schema('qualify',id=req(Ident),status=req(Literal['confirmed','false_positive']),reason=req(Text)),
 'incident.action':schema('incident_action',id=req(Ident),body=req(Text)),
 'incident.close':schema('incident_close',id=req(Ident),proof=req(Text)),
 'account.request':schema('account_request',target_id=opt(Ident),operation=req(Literal['create','suspend','reactivate','role']),role=opt(Role),name=opt(Title),username=opt(Ident),org_id=opt(Ident),reason=req(Text)),
 'account.approve':schema('account_approve',id=req(Ident)),
 'session.revoke':schema('session_revoke',id=req(Ident),reason=req(Text)),
 'certificate.request':schema('certificate',device_id=req(Ident),operation=req(Literal['renew','revoke']),reason=req(Text)),
 'patch.evaluate':schema('patch',id=req(Ident),priority=req(Literal['low','medium','high','critical']),exposure=req(Text),tests=req(Text),decision=req(Literal['review','approved','deferred']),reason=req(Text)),
 'deletion.request':schema('deletion',reason=req(Text)),
 'deletion.review':schema('deletion_review',id=req(Ident),reason=req(Text)),
 'access.check':schema('access_check'),
}


def iso(value=None):return datetime.fromtimestamp(time.time() if value is None else value,timezone.utc).isoformat()
def ident(prefix):return prefix+'-'+uuid.uuid4().hex
def fail(code=404,message='Ressource indisponible ou non autorisée.'):
    raise HTTPException(code,message)
def require_role(a,*roles):
    if a.role not in roles:fail()
def date_value(value):
    if not isinstance(value,str) or len(value)!=10:fail(422,'Date ISO YYYY-MM-DD requise.')
    try:return date.fromisoformat(value)
    except ValueError:fail(422,'Date invalide.')
def recent(session):
    if not session or getattr(session,'authenticated_at',0)<time.time()-300:
        fail(403,'Réauthentification récente requise.')
def configure(db,a):
    from .database import configure_actor
    configure_actor(db,a)
def rows(db,kind,*clauses):return list(db.scalars(select(R).where(R.kind==kind,*clauses).order_by(R.created_at.desc()).limit(500)))
def get(db,kind,record_id):
    r=db.get(R,record_id)
    if not r or r.kind!=kind:fail()
    return r
def add(db,kind,data,*,owner=None,patient=None,org=None,assigned=None,status='active',device=None,document=None,version=None):
    now=time.time();r=R(id=ident(kind),kind=kind,owner_id=owner,patient_id=patient,org_id=org,assigned_to=assigned,status=status,device_id=device,document_id=document,version=version,data=data,created_at=now,updated_at=now);db.add(r);db.flush();return r
def modify(r,**values):r.data={**r.data,**values};r.updated_at=time.time()
def record(r):
    out={**r.data,'id':r.id,'status':r.status,'created_at':iso(r.created_at),'updated_at':iso(r.updated_at)}
    for key in ['patient_id','document_id','version']:
        if getattr(r,key) is not None:out[key]=getattr(r,key)
    return out
def audit(db,a,action,target):
    # Never include command payloads, health content, credentials or session hashes.
    add(db,'audit',{'action':action,'target_id':target,'actor_id':a.id},owner=a.id)
def notify(db,owner,kind,title,route):
    add(db,'notification',{'kind':kind,'title':title,'route':route,'read':False},owner=owner)
def account_for_patient(db,patient):return db.scalar(select(Account).where(Account.patient_id==patient,Account.role=='user'))
def relation(db,patient,clinician):return db.scalar(select(CareLink).where(CareLink.patient_id==patient,CareLink.clinician_id==clinician,CareLink.enabled.is_(True)))
def grants(db,patient,clinician):
    if not relation(db,patient,clinician):return []
    return list(db.scalars(select(G).where(G.patient_id==patient,G.clinician_id==clinician,G.active.is_(True),G.expires>time.time())))
def patient_access(db,a,patient):
    if a.role=='user' and a.patient_id==patient:return True
    return a.role=='clinician' and bool(grants(db,patient,a.id))
def grant_json(g):return {k:getattr(g,k) for k in ('id','patient_id','clinician_id','start','end','categories','expires','active')}
def diagnostic(t):
    db=object_session(t)
    d=db.get(D,t.id) if db else None
    return bool(d and d.active and d.expires>time.time() and d.support_id==t.assigned_to and t.status!='resolved')
def ticket_access(db,a,record_id,support_only=False,active=False):
    t=get(db,'ticket',record_id)
    scope=db.get(SupportScope,(a.id,t.org_id)) if a.role=='support' else None
    permitted=a.role=='support' and t.assigned_to==a.id and scope and scope.active
    if not support_only:permitted=permitted or (a.role in {'user','clinician'} and t.owner_id==a.id)
    if not permitted:fail()
    if active and not diagnostic(t):fail(409,'Diagnostic temporaire fermé ou expiré.')
    return t
def device_access(db,a,device_id,ticket_id=None):
    d=get(db,'device',device_id)
    if a.role=='user' and d.owner_id==a.id:return d
    if a.role=='support' and ticket_id:
        t=ticket_access(db,a,ticket_id,support_only=True,active=True)
        if t.device_id==device_id:return d
    fail()
def make_job(db,a,kind,target,payload,owner=None,assigned=None,status='pending'):
    # Idempotent pending requests prevent repeated browser submissions becoming device commands.
    prior=db.scalar(select(J).where(J.kind==kind,J.target_id==target,J.status.in_(['pending','running','sent','awaiting_approval'])))
    if prior:fail(409,'Une opération de ce type est déjà en attente.')
    now=time.time();j=J(id=ident('job'),kind=kind,target_id=target,owner_id=owner or a.id,assigned_to=assigned,status=status,payload=payload,result={},created_at=now,updated_at=now);db.add(j);db.flush();return j
def session_public(s):return sha256(('skelivia-session-view:'+s.token_hash).encode()).hexdigest()


DEFAULT_SETTINGS={'large_text':False,'high_contrast':False,'pause_enabled':False,'pause_minutes':45,'channels':{'pause':'none','advice':'none','report':'none','support':'none','calibration':'none'},'quiet_start':'19:00','quiet_end':'08:00'}


def measurement_window(start=None,end=None):
    stop=date_value(end) if end else datetime.now(timezone.utc).date()
    begin=date_value(start) if start else stop-timedelta(days=29)
    if begin>stop or (stop-begin).days>=90:fail(422,'Période de 1 à 90 jours requise.')
    return str(begin),str(stop)


def _cursor(values):
    from .crypto import data_key
    raw=json.dumps(values,separators=(',',':')).encode()
    signature=hmac.digest(data_key(),b'measure-cursor-v1:'+raw,'sha256')
    return base64.urlsafe_b64encode(signature+raw).decode().rstrip('=')


def _read_cursor(value,scope):
    from .crypto import data_key
    try:
        if len(value)>2048:raise ValueError()
        raw=base64.urlsafe_b64decode(value+'='*((-len(value))%4));signature,data=raw[:32],raw[32:]
        if not hmac.compare_digest(signature,hmac.digest(data_key(),b'measure-cursor-v1:'+data,'sha256')):raise ValueError()
        decoded=json.loads(data)
        if not isinstance(decoded,list) or len(decoded)!=6 or decoded[:4]!=scope or not all(isinstance(v,str) for v in decoded):raise ValueError()
        return decoded[4:]
    except (ValueError,TypeError,UnicodeError,json.JSONDecodeError):fail(422,'Curseur invalide pour ce compte ou cette période.')


def measure_page(db,a,start=None,end=None,*,limit=1000,cursor=None,patient_id=None):
    require_role(a,'user','clinician')
    start,end=measurement_window(start,end)
    if a.role=='user':
        if patient_id and patient_id!=a.patient_id:fail()
        patient_ids=[a.patient_id]
    else:
        patient_ids=list(db.scalars(select(CareLink.patient_id).where(CareLink.clinician_id==a.id,CareLink.enabled.is_(True))))
        if patient_id:
            if patient_id not in patient_ids or not grants(db,patient_id,a.id):fail()
            patient_ids=[patient_id]
    day=func.substr(Report.recorded_at,1,10)
    query=select(Report).where(Report.patient_id.in_(patient_ids),day>=start,day<=end)
    grant_map={}
    if a.role=='clinician':
        grant_map={patient:grants(db,patient,a.id) for patient in patient_ids}
        scopes=[and_(Report.patient_id==patient,day>=g.start,day<=g.end) for patient,items in grant_map.items() for g in items if g.categories]
        query=query.where(or_(*scopes) if scopes else False)
    scope=[a.id,patient_id or '',start,end]
    if cursor:
        recorded,record_id=_read_cursor(cursor,scope)
        query=query.where(or_(Report.recorded_at<recorded,and_(Report.recorded_at==recorded,Report.id<record_id)))
    records=list(db.scalars(query.order_by(Report.recorded_at.desc(),Report.id.desc()).limit(limit+1)))
    more=len(records)>limit;records=records[:limit];output=[]
    for r in records:
        categories={'contact','pressure','moves'} if a.role=='user' else {c for g in grant_map[r.patient_id] if g.start<=r.recorded_at[:10]<=g.end for c in g.categories}
        allowed_keys={'contact':{'contact_seconds'},'pressure':{'thumb_pct','palm_pct'},'moves':{'episodes'}}
        keys=set().union(*(allowed_keys[c] for c in categories))
        metrics={k:v for k,v in r.metrics.items() if k in keys}
        output.append({'id':r.id,'patient_id':r.patient_id,'recorded_at':r.recorded_at,'quality':r.quality,'metrics':metrics,'window_start':r.metrics.get('window_start'),'window_end':r.metrics.get('window_end'),'window_duration_seconds':r.metrics.get('window_duration_seconds'),'calibration':r.metrics.get('calibration','C-DEMO-01' if r.synthetic else 'unknown'),'synthetic':r.synthetic,'categories':sorted(categories),'units':{'contact_seconds':'s','thumb_pct':'relative %','palm_pct':'relative %','episodes':'count'}})
    next_cursor=_cursor(scope+[records[-1].recorded_at,records[-1].id]) if more and records else None
    return {'measures':output,'window':{'start':start,'end':end},'limit':limit,'has_more':more,'next_cursor':next_cursor}


def measure_rows(db,a,start=None,end=None):
    """Compatibility helper: bounded page; exports must use export_measure_rows."""
    return measure_page(db,a,start,end)['measures'] if a.role in {'user','clinician'} else []


def export_measure_rows(db,a,start,end,cap=10000):
    require_role(a,'user')
    page=measure_page(db,a,start,end,limit=cap)
    if page['has_more']:fail(413,f'La période dépasse {cap} mesures. Réduisez la période ; aucun export partiel fourni.')
    return page['measures']


def workspace(db,a,current_session=None):
    settings=rows(db,'settings',R.owner_id==a.id)
    out={'role':a.role,'account':{'id':a.id,'name':a.name,'role':a.role},'settings':{**DEFAULT_SETTINGS,**(settings[0].data if settings else {})},'notifications':[record(n) for n in rows(db,'notification',R.owner_id==a.id)],'capabilities':{'hardware_results':'adapter_required','push':'not_configured','clinical':False},'server_time':iso(),'synthetic':False}
    if a.role!='employer':
        query=select(WebSession).where(WebSession.user_id.is_not(None),WebSession.expires>time.time())
        if a.role!='security':query=query.where(WebSession.user_id==a.id)
        out['sessions']=[{'id':session_public(s),'account_id':s.user_id,'expires':s.expires,'last_seen':s.last_seen,'current':bool(current_session and s.token_hash==current_session.token_hash)} for s in db.scalars(query)]
    if a.role in {'user','clinician'}:
        page=measure_page(db,a)
        out.update(measures=page['measures'],measure_window=page['window'],measure_limit=page['limit'],measures_has_more=page['has_more'],measures_next_cursor=page['next_cursor'])
        out['documents']=[record(r) for r in rows(db,'document') if patient_access(db,a,r.patient_id)]
        for document in out['documents']:
            if not document.get('author_name'):
                author=db.get(Account,document.get('author_id')) if document.get('author_id') else None
                document['author_name']=author.name if author else 'Professionnel non renseigné'
        out['tickets']=[ticket_json(r,a) for r in rows(db,'ticket',R.owner_id==a.id)]
        protected=out['measures']+out['documents']
        out['synthetic']=bool(protected) and all(r.get('synthetic') is True for r in protected)
    if a.role=='user':
        out['patient_id']=a.patient_id
        out['shares']=[grant_json(g) for g in db.scalars(select(G).where(G.owner_id==a.id))]
        links=list(db.scalars(select(CareLink.clinician_id).where(CareLink.patient_id==a.patient_id,CareLink.enabled.is_(True))))
        out['clinicians']=[{'id':c.id,'name':c.name} for c in db.scalars(select(Account).where(Account.id.in_(links),Account.active.is_(True),Account.role=='clinician'))]
        out['devices']=[device_json(r) for r in rows(db,'device',R.owner_id==a.id)]
        out['deletions']=[record(r) for r in rows(db,'deletion',R.owner_id==a.id)]
    elif a.role=='clinician':
        links=list(db.scalars(select(CareLink.patient_id).where(CareLink.clinician_id==a.id,CareLink.enabled.is_(True))))
        patients=list(db.scalars(select(Account).where(Account.patient_id.in_(links),Account.role=='user')))
        out['patients']=[{'id':p.patient_id,'name':p.name,'access':bool(grants(db,p.patient_id,a.id)),'shares':[grant_json(g) for g in grants(db,p.patient_id,a.id)]} for p in patients]
        out['organisations']=[{'id':o} for o in sorted({p.org_id for p in patients})]
        out['reminders']=[record(r) for r in rows(db,'reminder',R.owner_id==a.id,R.status!='deleted')]
        out['recommendations']=[record(r) for r in rows(db,'recommendation',R.owner_id==a.id)]
        out['measurement_updates']=[{'id':p.id,'title':p.data.get('title'),'version':p.data.get('version'),'comparability':p.data.get('comparability','Impact sur les mesures à vérifier avant comparaison.')} for p in rows(db,'patch',R.status=='approved')]
    elif a.role=='employer':out['recommendations']=[record(r) for r in rows(db,'recommendation',R.org_id==a.org_id)]
    elif a.role=='support':
        organisations=list(db.scalars(select(SupportScope.org_id).where(SupportScope.support_id==a.id,SupportScope.active.is_(True))))
        tickets=rows(db,'ticket',R.assigned_to==a.id,R.org_id.in_(organisations))
        out['tickets']=[ticket_json(t,a) for t in tickets]
        active_devices={t.device_id for t in tickets if diagnostic(t)}
        out['devices']=[device_json(d) for d in rows(db,'device',R.id.in_(active_devices))]
        out['approved_patches']=[{'id':p.id,'title':p.data.get('title'),'version':p.data.get('version')} for p in rows(db,'patch',R.status=='approved')]
    elif a.role=='security':
        from .security_monitor import snapshot
        out['runtime_status']=snapshot(db)
        out['accounts']=[{k:getattr(u,k) for k in ('id','name','role','org_id','active')} for u in db.scalars(select(Account))]
        for key,kind in [('account_requests','account_request'),('incidents','incident'),('patches','patch'),('components','component'),('proofs','proof'),('audit','audit'),('deletions','deletion')]:out[key]=[{**record(r),**({'requester_id':r.owner_id} if kind=='account_request' else {})} for r in rows(db,kind)]
        out['certificates']=[{'device_id':d.id,**d.data.get('certificate',{})} for d in rows(db,'device')]
    if a.role in {'user','support','security'}:
        query=select(J).order_by(J.created_at.desc()).limit(500)
        if a.role!='security':query=query.where((J.owner_id==a.id)|(J.assigned_to==a.id))
        jobs=list(db.scalars(query))
        if a.role=='support':
            ticket_ids={t.id for t in tickets};device_ids={t.device_id for t in tickets if t.device_id}
            jobs=[j for j in jobs if j.target_id in ticket_ids|device_ids]
        out['jobs']=[{'id':j.id,'kind':j.kind,'target_id':j.target_id,'status':j.status,'created_at':iso(j.created_at),'result':{k:v for k,v in j.result.items() if k in {'status','detail','verified_at','evidence_id'}}} for j in jobs]
    return out


def device_json(d):
    values={k:d.data.get(k) for k in ['connection','last_seen','firmware','calibration','calibration_status','history']}
    connection=values['connection'];age=None
    try:
        seen=datetime.fromisoformat(values['last_seen'].replace('Z','+00:00'))
        if seen.tzinfo is None:raise ValueError('Timezone required')
        age=time.time()-seen.timestamp()
        if age<0:raise ValueError('Future timestamp')
    except (ValueError,TypeError,AttributeError):age=None
    if connection not in {'retired','lost','revoked','disassociated'}:
        connection='unknown' if age is None else 'stale' if age>120 else connection or 'unknown'
    if d.data.get('certificate',{}).get('revoked'):connection='revoked'
    quality=d.data.get('last_quality','unknown')
    usable=connection=='connected' and age is not None and age<=120 and quality=='valid' and values['calibration_status'] in {'valid','verified','verified_local','synthetic_reference','réussie'}
    return {'id':d.id,'owner_id':d.owner_id,**values,'connection':connection,'quality':quality,'usable':usable,'freshness_seconds':age}


def ticket_json(t,a):
    data=t.data
    out={'id':t.id,'status':t.status,'created_at':iso(t.created_at),'owner_id':t.owner_id,'assigned_to':t.assigned_to,'device_id':t.device_id,'title':data.get('title'),'category':data.get('category'),'messages':data.get('messages',[]),'diagnostic_active':diagnostic(t),'diagnostic_expires':data.get('diagnostic_expires',0)}
    if a.role!='support' or diagnostic(t):out['checks']=data.get('checks',{})
    return out


def dispatch(db,a,action,p,session=None):
    result_id=None
    if action=='settings.save':
        values={k:v for k,v in p.items() if v is not None}
        if a.role!='user' and set(values)-{'large_text','high_contrast'}:fail()
        settings=rows(db,'settings',R.owner_id==a.id)
        if settings:modify(settings[0],**values);result_id=settings[0].id
        else:result_id=add(db,'settings',values,owner=a.id).id
    elif action=='notification.read':
        n=get(db,'notification',p['id'])
        if n.owner_id!=a.id:fail()
        modify(n,read=True)
    elif action=='pause.snooze':
        require_role(a,'user');settings=rows(db,'settings',R.owner_id==a.id)
        if settings:modify(settings[0],snoozed_until=time.time()+p['minutes']*60)
        else:add(db,'settings',{'snoozed_until':time.time()+p['minutes']*60},owner=a.id)
    elif action=='share.create':
        require_role(a,'user');start=date_value(p['start']);end=date_value(p['end'])
        c=db.get(Account,p['clinician_id'])
        if not c or c.role!='clinician' or not c.active or not relation(db,a.patient_id,c.id):fail()
        if start>end or (end-start).days>366 or end>datetime.now(timezone.utc).date():fail(422,'Période de partage invalide.')
        g=G(id=ident('share'),owner_id=a.id,patient_id=a.patient_id,clinician_id=c.id,start=str(start),end=str(end),categories=sorted(set(p['categories'])),expires=time.time()+p['duration_hours']*3600,active=True);db.add(g);result_id=g.id
    elif action=='share.revoke':
        require_role(a,'user');g=db.get(G,p['id'])
        if not g or g.owner_id!=a.id:fail()
        g.active=False
    elif action=='document.publish':
        require_role(a,'clinician')
        if not patient_access(db,a,p['patient_id']):fail()
        document=p.get('document_id');version=1
        if document:
            old=db.scalar(select(R).where(R.kind=='document',R.document_id==document).order_by(R.version.desc()))
            if not old or old.patient_id!=p['patient_id'] or old.owner_id!=a.id or old.data['kind']!=p['kind']:fail()
            version=old.version+1
        else:document=ident('document-series')
        r=add(db,'document',{'kind':p['kind'],'title':p['title'],'body':p['body'],'author_id':a.id,'author_name':a.name},owner=a.id,patient=p['patient_id'],document=document,version=version)
        u=account_for_patient(db,p['patient_id'])
        if u:notify(db,u.id,p['kind'],'Un document de votre soignant est disponible.','documents')
        result_id=r.id
    elif action=='reminder.create':
        require_role(a,'clinician');due=date_value(p['due'])
        if not relation(db,p['patient_id'],a.id):fail()
        result_id=add(db,'reminder',{'due':str(due),'body':p['body']},owner=a.id,patient=p['patient_id']).id
    elif action=='reminder.delete':
        require_role(a,'clinician');r=get(db,'reminder',p['id'])
        if r.owner_id!=a.id:fail()
        r.status='deleted';r.updated_at=time.time()
    elif action=='recommendation.publish':
        require_role(a,'clinician')
        linked=db.scalar(select(Account.id).join(CareLink,CareLink.patient_id==Account.patient_id).where(CareLink.clinician_id==a.id,CareLink.enabled.is_(True),Account.org_id==p['org_id'],Account.role=='user'))
        if not linked:fail()
        r=add(db,'recommendation',{'title':p['title'],'body':p['body'],'category':p['category'],'history':[{'status':'todo','at':iso(),'actor_id':a.id}]},owner=a.id,org=p['org_id'],status='todo');result_id=r.id
        for u in db.scalars(select(Account).where(Account.role=='employer',Account.org_id==p['org_id'],Account.active.is_(True))):notify(db,u.id,'recommendation','Une recommandation organisationnelle est disponible.','recommendations')
    elif action=='recommendation.status':
        require_role(a,'employer');r=get(db,'recommendation',p['id'])
        if r.org_id!=a.org_id:fail()
        r.status=p['status'];modify(r,history=[*r.data.get('history',[]),{'status':p['status'],'at':iso(),'actor_id':a.id}])
    elif action=='recommendation.revise':
        require_role(a,'clinician');r=get(db,'recommendation',p['id'])
        if r.owner_id!=a.id:fail()
        previous={k:r.data[k] for k in ('title','body','category')}
        modify(r,title=p['title'],body=p['body'],category=p['category'],history=[*r.data.get('history',[]),{'status':r.status,'at':iso(),'actor_id':a.id,'event':'revised','previous':previous}])
        for u in db.scalars(select(Account).where(Account.role=='employer',Account.org_id==r.org_id,Account.active.is_(True))):notify(db,u.id,'recommendation','Une recommandation organisationnelle a été modifiée.','recommendations')
    elif action=='ticket.create':
        require_role(a,'user','clinician');device=p.get('device_id')
        if device:
            d=get(db,'device',device)
            if a.role!='user' or d.owner_id!=a.id:fail()
        if a.role=='clinician' and p['category']!='software':fail(422,'Un ticket soignant concerne son logiciel, sans souris de patient.')
        support=db.scalar(select(Account).join(SupportScope,SupportScope.support_id==Account.id).where(Account.role=='support',SupportScope.org_id==a.org_id,SupportScope.active.is_(True),Account.active.is_(True)).order_by(Account.id))
        t=add(db,'ticket',{'title':p['title'],'category':p['category'],'messages':[{'author_id':a.id,'body':p['body'],'at':iso()}],'diagnostic_expires':0,'checks':{}},owner=a.id,org=a.org_id,assigned=support.id if support else None,status='in_progress',device=device);result_id=t.id
        if support:notify(db,support.id,'ticket','Un ticket technique vous est attribué.','tickets')
    elif action=='ticket.reply':
        t=ticket_access(db,a,p['id']);modify(t,messages=[*t.data.get('messages',[]),{'author_id':a.id,'body':p['body'],'at':iso()}])
        dest=t.owner_id if a.role=='support' else t.assigned_to
        if dest:notify(db,dest,'support','Une réponse technique est disponible.','tickets')
    elif action=='ticket.checks':
        t=ticket_access(db,a,p['id'],support_only=True,active=True);modify(t,checks={k:p[k] for k in ('connection','sensors','calibration')},checks_actor=a.id,checks_at=iso())
    elif action=='ticket.status':
        t=ticket_access(db,a,p['id'],support_only=True)
        if t.status=='resolved':fail(409,'Ticket déjà clôturé.')
        if p['status']=='resolved':
            if t.device_id:
                if not diagnostic(t) or not all(t.data.get('checks',{}).get(k) for k in ('connection','sensors','calibration')):fail(409,'Contrôles de remise en service requis.')
                d=get(db,'device',t.device_id)
                if d.data.get('calibration_status')!='verified':fail(409,'Résultat matériel vérifié requis ; une case cochée ne constitue pas une preuve.')
            modify(t,diagnostic_revoked=True)
            diagnostic_row=db.get(D,t.id)
            if diagnostic_row:diagnostic_row.active=False
        t.status=p['status'];notify(db,t.owner_id,'support','Le statut de votre ticket a évolué.','tickets')
    elif action=='diagnostic.request':
        t=ticket_access(db,a,p['id'],support_only=True)
        if not t.device_id or t.status=='resolved':fail(409,'Aucun diagnostic matériel disponible pour ce ticket.')
        j=make_job(db,a,'diagnostic_request',t.id,{'duration_minutes':p['duration_minutes'],'reason':p['reason']},owner=t.owner_id,assigned=a.id,status='awaiting_approval');result_id=j.id
        notify(db,t.owner_id,'support','Un diagnostic technique temporaire attend votre accord.','tickets')
    elif action=='diagnostic.approve':
        require_role(a,'user');j=db.get(J,p['id'])
        if not j or j.kind!='diagnostic_request' or j.owner_id!=a.id:fail()
        if j.status!='awaiting_approval':fail(409,'Demande déjà traitée.')
        t=ticket_access(db,a,j.target_id)
        if t.status=='resolved':fail(409,'Ticket clôturé.')
        expiry=time.time()+j.payload['duration_minutes']*60
        diagnostic_row=db.get(D,t.id)
        if diagnostic_row:
            diagnostic_row.expires=expiry;diagnostic_row.active=True;diagnostic_row.support_id=t.assigned_to
        else:db.add(D(ticket_id=t.id,device_id=t.device_id,support_id=t.assigned_to,owner_id=t.owner_id,expires=expiry,active=True))
        modify(t,diagnostic_expires=expiry,diagnostic_revoked=False);j.status='approved';j.updated_at=time.time();j.result={'status':'approved','detail':'Autorisation temporaire, aucun résultat matériel.'}
    elif action=='diagnostic.revoke':
        if a.role=='security':
            d=db.get(D,p['id'])
            if not d:fail()
            d.active=False
        else:
            t=ticket_access(db,a,p['id'],support_only=True);d=db.get(D,t.id)
            if d:d.active=False
            modify(t,diagnostic_revoked=True)
    elif action=='device.calibrate':
        d=device_access(db,a,p['device_id'],p.get('ticket_id'));result_id=make_job(db,a,'calibration',d.id,p,owner=d.owner_id,assigned=a.id if a.role=='support' else None).id
    elif action in {'device.update','device.replace'}:
        t=ticket_access(db,a,p['ticket_id'],support_only=True,active=True)
        if not t.device_id:fail(409,'Ce ticket ne concerne pas un appareil.')
        d=device_access(db,a,t.device_id,t.id)
        payload={**p,'device_id':d.id}
        if action=='device.update':
            patch=get(db,'patch',p['patch_id'])
            if patch.status!='approved':fail(409,'Correctif non approuvé.')
            payload['version']=patch.data['version'];kind='update'
        else:
            if db.get(R,p['new_device_id']):fail(409,'Identifiant déjà associé.')
            payload['old_device_id']=d.id;kind='replace'
        result_id=make_job(db,a,kind,d.id,payload,owner=t.owner_id,assigned=a.id).id
    elif action=='security.report':
        require_role(a,'user','clinician','support')
        if p.get('ticket_id'):ticket_access(db,a,p['ticket_id'],support_only=a.role=='support')
        r=add(db,'incident',{'title':'Signalement technique à examiner','body':p['body'],'ticket_id':p.get('ticket_id'),'timeline':[]},owner=a.id,status='review');result_id=r.id
    elif action.startswith('incident.'):
        require_role(a,'security');r=get(db,'incident',p['id']);timeline=list(r.data.get('timeline',[]))
        if r.status=='closed':fail(409,'Incident déjà clôturé.')
        if action=='incident.qualify':
            if r.status!='review':fail(409,'Événement déjà qualifié.')
            r.status=p['status'];timeline.append({'type':'qualification','body':p['reason'],'at':iso(),'author_id':a.id})
        elif action=='incident.action':
            if r.status!='confirmed':fail(409,'Confirmer l’incident avant de consigner une action.')
            timeline.append({'type':'action','body':p['body'],'at':iso(),'author_id':a.id})
        else:
            if r.status!='confirmed' or not any(e['type']=='action' for e in timeline):fail(409,'Action de traitement requise.')
            r.status='closed';timeline.append({'type':'verification','body':p['proof'],'at':iso(),'author_id':a.id})
        modify(r,timeline=timeline)
    elif action=='account.request':
        require_role(a,'security');recent(session)
        if p['operation']!='create':
            target=db.get(Account,p.get('target_id')) if p.get('target_id') else None
            if not target or target.id==a.id:fail()
        else:
            if not all(p.get(k) for k in ('username','name','role','org_id')):fail(422,'Identité, organisation et rôle requis.')
            if p.get('target_id'):fail(422,'La cible est attribuée par le provisionnement.')
        if p['operation']=='role' and not p.get('role'):fail(422,'Rôle requis.')
        result_id=add(db,'account_request',p,owner=a.id,status='pending').id
    elif action=='account.approve':
        require_role(a,'security');recent(session);r=get(db,'account_request',p['id'])
        if r.status!='pending':fail(409,'Demande déjà traitée.')
        if r.owner_id==a.id or r.data.get('target_id')==a.id:fail(403,'Approbateur distinct du demandeur et de la cible requis.')
        operation=r.data['operation']
        if operation=='create':
            result_id=make_job(db,a,'account_provision',r.id,{**r.data,'requester_id':r.owner_id,'approver_id':a.id}).id;r.status='approved_pending_provision'
        else:
            target=db.get(Account,r.data['target_id'])
            if not target:fail()
            if operation=='role':target.role=r.data['role']
            else:target.active=operation=='reactivate'
            # Never resurrect existing sessions after a suspension or role change.
            db.execute(delete(WebSession).where(WebSession.user_id==target.id));r.status='approved'
        modify(r,approver_id=a.id,approved_at=iso())
    elif action=='session.revoke':
        require_role(a,'user','clinician','support','security')
        query=select(WebSession).where(WebSession.user_id.is_not(None))
        if a.role!='security':query=query.where(WebSession.user_id==a.id)
        target=next((s for s in db.scalars(query) if session_public(s)==p['id']),None)
        if not target:fail()
        if target.user_id!=a.id:recent(session)
        db.delete(target)
    elif action=='certificate.request':
        require_role(a,'security');recent(session);d=get(db,'device',p['device_id'])
        result_id=make_job(db,a,'certificate',d.id,p).id
    elif action=='patch.evaluate':
        require_role(a,'security');recent(session);r=get(db,'patch',p['id'])
        if p['decision']=='approved' and (r.owner_id==a.id or r.data.get('evaluator_id')==a.id):fail(403,'L’approbation exige un second administrateur.')
        if p['decision']=='approved' and not r.data.get('evaluator_id'):fail(409,'Évaluation préalable par un autre administrateur requise.')
        changes={k:p[k] for k in ('priority','exposure','tests','reason')}
        if p['decision']=='approved':changes['approver_id']=a.id
        else:changes['evaluator_id']=a.id
        modify(r,**changes);r.status=p['decision']
    elif action=='deletion.request':
        require_role(a,'user');recent(session)
        if rows(db,'deletion',R.owner_id==a.id,R.status.in_(['requested','pending'])):fail(409,'Une demande est déjà en cours.')
        result_id=add(db,'deletion',{'reason':p['reason'],'history':[{'status':'requested','at':iso()}]},owner=a.id,patient=a.patient_id,status='requested').id
    elif action=='deletion.review':
        require_role(a,'security');recent(session);r=get(db,'deletion',p['id'])
        if r.status!='requested':fail(409,'Demande déjà prise en charge.')
        result_id=make_job(db,a,'deletion',r.id,{'account_id':r.owner_id,'review_reason':p['reason']}).id;r.status='pending';modify(r,history=[*r.data.get('history',[]),{'status':'pending','at':iso()}])
    elif action=='access.check':
        require_role(a,'security')
        expired=list(db.scalars(select(G).where(G.expires<=time.time())))
        diagnostics=list(db.scalars(select(D)))
        result_id=add(db,'proof',{'kind':'access_check','expired_grants':len(expired),'closed_diagnostics':sum(not d.active or d.expires<=time.time() for d in diagnostics),'active_diagnostics':sum(d.active and d.expires>time.time() for d in diagnostics),'description':'Contrôle des états de la base applicative uniquement ; aucune preuve de pare-feu ou broker.','verified':True,'at':iso()},owner=a.id,status='database_checked').id
    else:fail(422,'Action non prise en charge.')
    audit(db,a,action,result_id or p.get('id') or p.get('device_id') or a.id)
    return {'ok':True,**({'id':result_id} if result_id else {})}


def install_domain(app,factory,account_dep,csrf_dep):
    def db_dep(a=Depends(account_dep)):
        with factory() as db:
            configure(db,a)
            current=db.get(Account,a.id)
            if not current or not current.active:fail(401,'Compte inactif.')
            configure(db,current)
            yield db

    @app.get('/api/workspace')
    def get_workspace(request:Request,a=Depends(account_dep),db=Depends(db_dep)):
        # Session metadata is read server-side; hashes never leave the service.
        token=request.cookies.get(getattr(app.state,'session_cookie','skelivia_session'),'')
        current=db.get(WebSession,sha256(token.encode()).hexdigest()) if token else None
        actor=db.get(Account,a.id)
        output=workspace(db,actor,current)
        consulted={r['patient_id'] for key in ('measures','documents') for r in output.get(key,[]) if r.get('patient_id')}
        if consulted:
            for patient in sorted(consulted):audit(db,actor,'medical.workspace.read',patient)
        else:audit(db,actor,'workspace.read',actor.id)
        db.commit()
        return output

    @app.post('/api/actions')
    def action(body:Envelope,a=Depends(account_dep),session=Depends(csrf_dep),db=Depends(db_dep)):
        model=SCHEMAS.get(body.action)
        if not model:fail(422,'Action inconnue ou non autorisée.')
        try:p=model.model_validate(body.payload).model_dump()
        except ValidationError as exc:
            raise HTTPException(422,[{'loc':e['loc'],'msg':e['msg'],'type':e['type']} for e in exc.errors()]) from None
        try:
            result=dispatch(db,db.get(Account,a.id),body.action,p,session);db.commit();return result
        except HTTPException:
            db.rollback();configure(db,a)
            audit(db,a,'denied.'+body.action,a.id);db.commit()
            raise
        except IntegrityError:
            db.rollback();fail(409,'Modification concurrente ; rechargez les données.')

    @app.get('/api/measures')
    def get_measures(start:str,end:str,limit:int=Query(default=1000,ge=1,le=1000),cursor:str|None=Query(default=None,max_length=2048),patient_id:str|None=Query(default=None,max_length=80),a=Depends(account_dep),db=Depends(db_dep)):
        actor=db.get(Account,a.id)
        result=measure_page(db,actor,start,end,limit=limit,cursor=cursor,patient_id=patient_id)
        for patient in sorted({r['patient_id'] for r in result['measures']}):audit(db,actor,'medical.measures.read',patient)
        db.commit();return result

    @app.get('/api/simulation-notifications')
    def simulation_notifications(run_id:uuid.UUID,a=Depends(account_dep),db=Depends(db_dep)):
        actor=db.get(Account,a.id)
        require_role(actor,'user')
        checked=time.time()
        # SensitiveJSON cannot be filtered safely with SQL JSON operators. Limit
        # before decrypting, and disclose truncation before claiming an absence.
        candidates=list(db.scalars(select(R).where(R.kind=='notification',R.owner_id==actor.id,R.created_at>=checked-86400)
            .order_by(R.created_at.desc(),R.id.desc()).limit(501)))
        result=[]
        from .usage_events import TITLES
        for notice in candidates[:500]:
            data=notice.data
            if data.get('synthetic') is not True or data.get('simulation_run')!=str(run_id):continue
            if data.get('event_kind') not in TITLES or data.get('origin') not in {'computed','manual'}:continue
            sequence=data.get('sequence')
            if not isinstance(sequence,int) or isinstance(sequence,bool) or sequence<0:continue
            result.append({'id':notice.id,'title':data.get('title','Simulation'),'event_kind':data['event_kind'],
                'origin':data['origin'],'created_at':iso(notice.created_at),'sequence':sequence})
        return {'run_id':str(run_id),'notifications':result,'checked_at':iso(checked),'truncated':len(candidates)>500,'scope':'own_notifications'}

    @app.get('/api/export')
    def export(kind:str,start:str|None=None,end:str|None=None,a=Depends(account_dep),db=Depends(db_dep)):
        if kind=='personal':
            require_role(a,'user')
            if not start or not end or date_value(start)>date_value(end):fail(422,'Période requise.')
            result={'period':{'start':start,'end':end},'measures':export_measure_rows(db,a,start,end),'notice':'Unités relatives ; valeurs absentes explicitement nulles. Aucune conclusion médicale.'}
        elif kind=='prevention':
            require_role(a,'employer');result={'recommendations':[record(r) for r in rows(db,'recommendation',R.org_id==a.org_id)]}
        else:fail()
        audit(db,a,'export.'+kind,a.id);db.commit()
        return JSONResponse(result,headers={'Content-Disposition':'attachment; filename="skelivia-'+kind+'.json"'})
