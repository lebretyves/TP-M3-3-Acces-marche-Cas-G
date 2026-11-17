"""Banc local à données fictives. Aucun mode de production implicite."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import hmac
import secrets
import time
import os
import logging
from urllib.parse import urlparse
from typing import Literal
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
import pyotp
from sqlalchemy import delete, select, update
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .database import database
from .models import Account, Alert, Audit, CareLink, LoginLimit, Prevention, Report, Share, Ticket, WebSession

COOKIE='skelivia_session'
ORIGINS={'http://127.0.0.1:8766','http://localhost:8766','http://127.0.0.1:8772','http://localhost:8772'}
ENV={'label':'Banc local à données fictives','auth':'local_mfa','database':'sqlite','clinical':False}
NOTICE='Bilan fictif figé, sans liaison aux capteurs. Les pourcentages d’appui ne sont ni des forces en newtons ni un risque de TMS. Aucun suivi médical réel.'
PH=PasswordHasher()
DUMMY=PH.hash(secrets.token_urlsafe(20))


class RedactAccessQuery(logging.Filter):
    def filter(self, record):
        if isinstance(record.args,tuple) and len(record.args)==5:
            values=list(record.args)
            values[2]=str(values[2]).split('?',1)[0]
            record.args=tuple(values)
        return True


logging.getLogger('uvicorn.access').addFilter(RedactAccessQuery())


def stamp(value=None):
    return datetime.fromtimestamp(time.time() if value is None else value,timezone.utc).isoformat()


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


class StrictBody(BaseModel):
    model_config=ConfigDict(extra='forbid')


class LoginBody(StrictBody):
    username: str=Field(min_length=1,max_length=80)
    password: str=Field(min_length=1,max_length=200)
    otp: str=Field(pattern=r'^\d{6}$')


class ShareBody(StrictBody):
    report_id: str=Field(max_length=60)
    clinician_id: str=Field(max_length=60)
    duration_hours: int=Field(default=24,ge=1,le=72,strict=True)


class TicketBody(StrictBody):
    category: Literal['connexion','capteur','affichage']


def create_app(db_url=None, *, testing=False):
    mode=os.getenv('SKELIVIA_AUTH_MODE','local')
    if mode not in {'local','oidc'}: raise RuntimeError('Unknown authentication mode.')
    origin=os.getenv('SKELIVIA_PUBLIC_ORIGIN','http://127.0.0.1:8772').rstrip('/')
    if mode=='oidc' and not origin.startswith('https://'): raise RuntimeError('HTTPS required for OIDC service.')
    origins={origin} if mode=='oidc' else ORIGINS|{origin}
    secure=mode=='oidc'
    engine, factory=database(db_url)
    app=FastAPI(title='Souris P2 - banc fictif',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.factory=factory;app.state.engine=engine
    app.state.session_cookie=COOKIE
    environment={**ENV,'database':engine.dialect.name,'auth':mode,'label':'SKELIVIA ? environnement de validation','synthetic_only':True}
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=list({'127.0.0.1','localhost',urlparse(origin).hostname}))

    @app.middleware('http')
    async def boundary(request,call_next):
        if mode=='local' and not testing and (not request.client or request.client.host not in {'127.0.0.1','::1'}):
            return JSONResponse({'detail':'Ce banc est limité au poste local.'},403)
        length=request.headers.get('content-length','0')
        if not length.isdigit() or int(length)>8192:
            return JSONResponse({'detail':'Requête trop volumineuse.'},413)
        # The loopback simulator may open this inert entry page. API requests and
        # mutations retain the existing same-origin, session and CSRF boundary.
        simulator_entry=(request.method=='GET' and request.url.path=='/static/simulation.html'
                         and request.headers.get('sec-fetch-mode')=='navigate'
                         and request.headers.get('sec-fetch-dest')=='document')
        if request.headers.get('sec-fetch-site')=='cross-site' and not simulator_entry:
            return JSONResponse({'detail':'Origine refusée.'},403)
        if request.method not in {'GET','HEAD','OPTIONS'} and request.url.path!='/oidc/backchannel-logout':
            if request.headers.get('origin') not in origins:
                return JSONResponse({'detail':'Origine refusée.'},403)
            if request.headers.get('content-type','').split(';')[0]!='application/json':
                return JSONResponse({'detail':'Format JSON requis.'},415)
            data=await request.body()
            if len(data)>8192:return JSONResponse({'detail':'Requête trop volumineuse.'},413)
        response=await call_next(request)
        # Only this inert launcher may be embedded by our own origin. Its data
        # and commands still use the ordinary account, object and CSRF checks.
        framed_launcher=request.url.path=='/static/simulation.html'
        frame_policy="'self'" if framed_launcher else "'none'"
        response.headers.update({'Cache-Control':'no-store','Pragma':'no-cache','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'SAMEORIGIN' if framed_launcher else 'DENY','Permissions-Policy':'camera=(), microphone=(), geolocation=()','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors "+frame_policy+"; form-action 'self'"})
        if secure: response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    def db_dep():
        with factory() as db:yield db

    def session(request,db):
        token=request.cookies.get(COOKIE,'')
        s=db.get(WebSession,hashed(token)) if token else None
        if not s or s.expires<=time.time() or s.last_seen<time.time()-900:
            if s:db.delete(s);db.commit()
            return None
        return s

    def audit(db,actor,event,result='ok'):
        db.add(Audit(at=stamp(),actor_id=actor.id if actor else 'anonyme',event=event,result=result))

    def deny(db,actor=None):
        audit(db,actor,'acces_refuse','refus');db.commit()
        raise HTTPException(404,'Ressource indisponible ou non autorisée.')

    def account(request:Request,db=Depends(db_dep)):
        s=session(request,db)
        a=db.get(Account,s.user_id) if s and s.user_id else None
        if not a or not a.active:raise HTTPException(401,'Connexion requise ou session expirée.')
        s.last_seen=time.time();db.commit()
        return a

    def csrf(request:Request,db=Depends(db_dep)):
        s=session(request,db)
        if not s or not hmac.compare_digest(s.csrf,request.headers.get('x-csrf-token','')):
            raise HTTPException(403,'Session invalide. Rechargez la page.')
        return s

    def issue(db,response,ident=None,*,auth_time=None,oidc_sid=None):
        db.execute(delete(WebSession).where(WebSession.expires<time.time()))
        token=secrets.token_urlsafe(32)
        s=WebSession(token_hash=hashed(token),user_id=ident,csrf=secrets.token_urlsafe(32),expires=time.time()+1800,last_seen=time.time(),authenticated_at=(auth_time or time.time()) if ident else 0,oidc_sid=oidc_sid)
        db.add(s);db.commit()
        # HTTP uniquement sur loopback ; HTTPS + Secure requis hors de ce banc.
        response.set_cookie(COOKIE,token,httponly=True,samesite='lax' if secure else 'strict',secure=secure,max_age=1800,path='/')
        return s

    def user_json(a):
        return {k:getattr(a,k) for k in ('id','username','name','role','org_id','patient_id')}

    def session_json(db,s):
        a=db.get(Account,s.user_id) if s.user_id else None
        return {'authenticated':bool(a and a.active),'csrf_token':s.csrf,'user':user_json(a) if a and a.active else None,'environment':environment,'accounts':[{'username':x.username,'name':x.name,'role':x.role} for x in db.scalars(select(Account).order_by(Account.username))] if mode=='local' else [],'login_url':'/oidc/login' if mode=='oidc' else None}

    def relation(db,patient,clinician):
        return db.scalar(select(CareLink).where(CareLink.patient_id==patient,CareLink.clinician_id==clinician,CareLink.enabled.is_(True)))

    def active_share(db,r,clinician):
        if not relation(db,r.patient_id,clinician):return None
        return db.scalar(select(Share).where(Share.report_id==r.id,Share.clinician_id==clinician,Share.active.is_(True),Share.expires>time.time()))

    def report_access(db,a,ident):
        r=db.get(Report,ident)
        if not r or not r.synthetic:deny(db,a)
        if a.role=='user' and a.patient_id==r.patient_id:return r,None
        if a.role=='clinician':
            shared=active_share(db,r,a.id)
            if shared:return r,shared
        deny(db,a)

    def report_json(r,summary=False):
        out={k:getattr(r,k) for k in ('id','patient_id','title','recorded_at','synthetic','quality')}
        out['notice']=NOTICE
        if not summary:out['metrics']=r.metrics
        return out

    def ticket_json(t):return {k:getattr(t,k) for k in ('id','category','device_id','status')}

    @app.get('/api/health')
    def health():return {'status':'ok','mode':'local_synthetic','clinical':False}

    @app.get('/api/session')
    def get_session(request:Request,response:Response,db=Depends(db_dep)):
        s=session(request,db)
        if s and s.user_id:
            a=db.get(Account,s.user_id)
            if not a or not a.active:db.delete(s);db.commit();s=None
        if not s:s=issue(db,response)
        return session_json(db,s)

    @app.post('/api/login')
    def login(body:LoginBody,request:Request,response:Response,db=Depends(db_dep),s=Depends(csrf)):
        if mode!='local': raise HTTPException(404,'Local authentication disabled.')
        now=time.time()
        # Deux limites : compte (plusieurs IP) et client local (plusieurs comptes).
        for key in [hashed('account:'+body.username.casefold()),hashed('ip:'+request.client.host)]:
            rate=db.get(LoginLimit,key)
            if not rate:rate=LoginLimit(key=key,start=now,count=0);db.add(rate)
            if now-rate.start>600:rate.start=now;rate.count=0
            if rate.count>=12:
                db.commit();raise HTTPException(429,'Trop de tentatives. Réessayez dans dix minutes.')
            rate.count+=1;db.commit()
        a=db.scalar(select(Account).where(Account.username==body.username))
        try:valid=PH.verify(a.password_hash if a else DUMMY,body.password)
        except VerificationError:valid=False
        counter=int(now//30)
        found=next((c for c in (counter-1,counter,counter+1) if a and hmac.compare_digest(pyotp.TOTP(a.otp_secret).at(c*30),body.otp)),None)
        if not valid or not a or not a.active or found is None or found<=a.otp_last_counter:
            audit(db,None,'connexion_refusee','refus');db.commit()
            raise HTTPException(401,'Identifiants ou code invalides. Un code déjà utilisé ne peut pas être réemployé.')
        changed=db.execute(update(Account).where(Account.id==a.id,Account.otp_last_counter<found).values(otp_last_counter=found))
        if changed.rowcount!=1:db.rollback();raise HTTPException(401,'Code déjà utilisé.')
        db.delete(s);audit(db,a,'connexion_mfa');db.commit()
        s=issue(db,response,a.id)
        from .login_activity import record_login
        record_login(db,a,request,response,secure=secure)
        return session_json(db,s)

    @app.post('/api/logout')
    def logout(response:Response,db=Depends(db_dep),s=Depends(csrf)):
        a=db.get(Account,s.user_id) if s.user_id else None
        audit(db,a,'deconnexion');db.delete(s);db.commit()
        response.delete_cookie(COOKIE,path='/',httponly=True,secure=secure,samesite='lax' if secure else 'strict')
        return {'ok':True}

    class ReauthBody(StrictBody):
        password: str=Field(min_length=1,max_length=200)
        otp: str=Field(pattern=r'^\d{6}$')

    @app.post('/api/reauth')
    def reauthenticate(body:ReauthBody,request:Request,response:Response,db=Depends(db_dep),s=Depends(csrf),a=Depends(account)):
        return login(LoginBody(username=a.username,password=body.password,otp=body.otp),request,response,db,s)

    from .domain import install_domain
    install_domain(app,factory,account,csrf)
    from .push import install_push
    install_push(app,factory,account,csrf)
    from .fhir import install_fhir
    install_fhir(app,factory,account)
    if mode=='oidc':
        from .auth_oidc import install_oidc
        install_oidc(app,factory,issue,session_json,COOKIE,origin)

    static=Path(__file__).parent/'static';static.mkdir(exist_ok=True)
    app.mount('/static',StaticFiles(directory=static),name='static')

    @app.get('/')
    def index():return FileResponse(static/'index.html')

    return app


# Uvicorn utilise --factory : aucune création de base lors d'un simple import.
