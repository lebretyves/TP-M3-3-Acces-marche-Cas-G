"""Local operator simulator: no database credentials and no browser device secrets."""
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import secrets
import threading
import time
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse,RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from transport import Publisher,TransportUnavailable
from live_samples import chart_samples

ROOT=Path(__file__).resolve().parent
EVENT_KINDS=('pause_reminder','high_force','quiet_contact','absent')
EventKind=Literal['pause_reminder','high_force','quiet_contact','absent']


class EventRequest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    kind:EventKind


class Manual(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,allow_inf_nan=False)
    ax:float=0.;ay:float=0.;az:float=9.80665
    gx:float=0.;gy:float=0.;gz:float=0.
    thumb:int=Field(default=1000,ge=0,le=4095)
    palm:int=Field(default=1000,ge=0,le=4095)
    contact:bool=True
    @field_validator('ax','ay','az','gx','gy','gz')
    @classmethod
    def bounded(cls,value):
        if abs(value)>100:raise ValueError('Valeur de démonstration hors limite.')
        return value


class Assumptions(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    thumb:int=Field(ge=0,le=4095)
    palm:int=Field(ge=0,le=4095)
    contact:bool


class RunConfig(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    source:Literal['wokwi','phyphox']='wokwi'
    mode:Literal['manual','normal','intensive','force','immobile','invalid','network_cut']='normal'
    duration_seconds:int=Field(default=30,ge=5,le=300,multiple_of=5)
    step_ms:Literal[50]=50
    dataset_id:str|None=Field(default=None,max_length=100)
    manual:Manual=Field(default_factory=Manual)
    replay_assumptions:Assumptions|None=None
    event_kinds:list[EventKind]=Field(default_factory=lambda:list(EVENT_KINDS),max_length=4)
    delivery_mode:Literal['dashboard','local']='dashboard'
    fault_sensor:Literal['all','thumb','palm','motion','contact']='all'

    @model_validator(mode='after')
    def targeted_fault_context(self):
        if self.fault_sensor!='all' and (self.source!='wokwi' or self.mode!='invalid'):
            raise ValueError('Une panne ciblée exige le scénario Capteur invalide de Wokwi.')
        return self

    @field_validator('event_kinds')
    @classmethod
    def unique_events(cls,value):
        if len(value)!=len(set(value)):raise ValueError('Événements dupliqués.')
        return value


def stamp(value=None):return datetime.fromtimestamp(value or time.time(),timezone.utc).isoformat()


class Controller:
    def __init__(self,build,publisher=None,output_dir=None):
        self.build=build;self.publisher=publisher or Publisher()
        self.output_dir=Path(output_dir or os.getenv('SIMULATOR_OUTPUT_DIR',str(ROOT/'.runtime/runs')))
        self.lock=threading.RLock();self.wake=threading.Event();self.thread=None;self.generation=0
        self.pending_events={}
        self.chart=[]
        self.state={'status':'idle','run_id':None,'windows':[],'events':[],'progress_seconds':0,'total_seconds':0,'broker_accepted':0,'skipped_windows':0,'error':None}

    def snapshot(self):
        with self.lock:
            result=deepcopy(self.state)
            elapsed=result.get('elapsed_seconds',result.get('progress_seconds',0))
            result['chart_samples']=[p.copy() for p in self.chart if p['time_seconds']<elapsed]
            result['detected_events']=[deepcopy(e) for e in result.get('events_expected',[]) if e.get('at_seconds',0)<elapsed]
            result['detected_events'].extend(e.copy() for e in result.get('events',[]) if e.get('origin')=='manual')
            return result

    def prepare(self,config):
        engine_config={k:v for k,v in config.items() if k not in ('event_kinds','delivery_mode')}
        engine_config['include_samples']=True
        plan=deepcopy(self.build(engine_config))
        plan['chart_samples']=chart_samples(plan.pop('samples',[]))
        selected=config.get('event_kinds',list(EVENT_KINDS))
        for window in plan['windows']:
            window['events_to_send']=[{**e,'origin':'computed'} for e in window.get('events',[]) if e['kind'] in selected and window['quality']=='valid' and window.get('publish',True)]
        plan.setdefault('provenance',{})['event_kinds']=selected
        plan['provenance']['delivery_mode']=config.get('delivery_mode','dashboard')
        if config.get('delivery_mode','dashboard')=='local':
            plan.setdefault('summary',{})['publishable_windows']=0
        return plan

    def enqueue_event(self,kind):
        with self.lock:
            config=self.state.get('config',{})
            if self.state['status']!='running':raise HTTPException(409,'Lancez une transmission avant de déclencher un événement.')
            if (config.get('source')=='wokwi' and config.get('mode') in ('invalid','network_cut')) or (config.get('source')=='phyphox' and config.get('replay_assumptions') is None):
                raise HTTPException(409,'Ce scénario ne transmet pas de mesures valides.')
            if config.get('delivery_mode','dashboard')=='dashboard' and self.publisher.meta.get('calibration_status') not in ('valid','verified','réussie','verified_local','synthetic_reference'):
                raise HTTPException(409,'La référence de calibration est requise.')
            if kind in self.pending_events:raise HTTPException(409,'Cet événement attend déjà la prochaine fenêtre.')
            self.pending_events[kind]=time.time()
            self.state['pending_events']=list(self.pending_events)
            return {'status':'queued','kind':kind,'run_id':self.state['run_id'],'detail':'En attente de la prochaine fenêtre valide ; aucune alerte reçue n’est encore confirmée.'}

    def start(self,config):
        with self.lock:
            if self.state['status'] in ('preparing','running','paused','stopping') or (self.thread and self.thread.is_alive()):raise HTTPException(409,'Une exécution est déjà active.')
            self.state={'status':'preparing','run_id':str(uuid4()),'config':config,'windows':[],'events':[],'progress_seconds':0,'total_seconds':config['duration_seconds'],'broker_accepted':0,'skipped_windows':0,'error':None,'started_at':stamp()}
            self.pending_events={};self.state['pending_events']=[]
            self.chart=[];self.state['elapsed_seconds']=0
        try:
            plan=self.prepare(config)
            if config.get('delivery_mode','dashboard')=='dashboard':
                self.publisher.connect()
                if config['source']=='wokwi' and config['mode']=='network_cut':self.publisher.close()
        except Exception as error:
            self.publisher.close()
            with self.lock:self.state['status']='failed';self.state['error']=str(error) if isinstance(error,(ValueError,TransportUnavailable)) else 'Préparation du simulateur impossible.'
            raise HTTPException(409,self.state['error']) from None
        with self.lock:
            self.state.update(status='running',summary=plan.get('summary',{}),provenance=plan.get('provenance',{}),events_expected=plan.get('events_expected',[]))
            self.chart=plan.get('chart_samples',[])
            self.wake.clear();self.generation+=1
            self.thread=threading.Thread(target=self.execute,args=(plan,),daemon=True);self.thread.start()
            return self.snapshot()

    def control(self,action):
        with self.lock:
            current=self.state['status']
            if action=='pause' and current=='running':self.state['status']='paused';self.state['elapsed_seconds']=self.state['progress_seconds']
            elif action=='resume' and current=='paused':self.state['status']='running'
            elif action=='stop' and current in ('running','paused'):self.state['status']='stopping';self.state['elapsed_seconds']=self.state['progress_seconds']
            else:raise HTTPException(409,'Cette action ne correspond pas à l’état de l’exécution.')
            self.generation+=1;self.wake.set();return self.snapshot()

    def wait_window(self,duration):
        deadline=None;started=None;generation=None
        while True:
            with self.lock:
                status=self.state['status'];current_generation=self.generation
            if status=='stopping':return None
            if status=='paused':deadline=None;self.wake.wait(.1);self.wake.clear();continue
            if deadline is None or generation!=current_generation:
                # Any interrupted partial interval is discarded, never counted as contact.
                deadline=time.monotonic()+duration;started=time.time();generation=current_generation
            with self.lock:
                if self.state['status']=='running' and self.generation==generation:
                    self.state['elapsed_seconds']=min(self.state['total_seconds'],self.state['progress_seconds']+max(0.,duration-(deadline-time.monotonic())))
            if time.monotonic()>=deadline:return started,time.time()
            self.wake.wait(min(.1,max(0,deadline-time.monotonic())));self.wake.clear()

    def execute(self,plan):
        try:
            for sequence,window in enumerate(plan['windows']):
                while True:
                    timing=self.wait_window(float(window['duration_seconds']))
                    with self.lock:
                        if timing is None or self.state['status']=='running':break
                if timing is None:break
                start,end=timing
                with self.lock:
                    run_id=self.state['run_id']
                    local_only=self.state['config'].get('delivery_mode','dashboard')=='local'
                visible=deepcopy(window);visible['window_start']=stamp(start);visible['measured_at']=stamp(end)
                selected={e['kind']:{'kind':e['kind'],'at_seconds':round(e['at_seconds']-window['start_seconds'],9),'origin':'computed'} for e in window.get('events_to_send',[])}
                visible['events_sent']=[];visible['events_suppressed']=[]
                if local_only:
                    visible['delivery']='local_only'
                    if window['quality']=='valid':
                        with self.lock:
                            pending={k:v for k,v in self.pending_events.items() if v<=end}
                            self.pending_events={k:v for k,v in self.pending_events.items() if v>end}
                            self.state['pending_events']=list(self.pending_events)
                        visible['events_local']=[{'kind':k,'origin':'manual','at_seconds':max(0.,min(end-start,v-start))} for k,v in pending.items()]
                elif window.get('publish',True):
                    meta=self.publisher.meta
                    quality=window['quality']
                    if quality=='valid' and meta.get('calibration_status') not in ('valid','verified','réussie','verified_local','synthetic_reference'):
                        visible['computed_quality']=quality
                        quality='calibration_required';visible['quality']=quality
                        visible['metrics']=None
                    metrics=window.get('metrics') if quality=='valid' else None
                    if end<=start or (metrics and metrics['contact_seconds']>end-start):raise TransportUnavailable('Horloge incohérente : intervalle non transmis.')
                    if quality=='valid':
                        with self.lock:
                            pending={k:v for k,v in self.pending_events.items() if v<=end}
                            self.pending_events={k:v for k,v in self.pending_events.items() if v>end}
                            self.state['pending_events']=list(self.pending_events)
                        for kind,queued_at in pending.items():
                            selected[kind]={'kind':kind,'at_seconds':max(0.,min(end-start,queued_at-start)),'origin':'manual'}
                    # No packet contains original acquisition dates, subject identities or raw signals.
                    packet={'schema_version':'skelivia.telemetry.v1','synthetic':True,'device_id':meta['device_id'],'session_id':run_id,'sequence':sequence,
                            'window_start':stamp(start),'measured_at':stamp(end),'firmware_version':meta['firmware_version'],'algorithm_version':meta['algorithm_version'],
                            'calibration_version':meta['calibration_version'],'quality':quality,'metrics':metrics}
                    if quality=='valid':packet['events']=list(selected.values())
                    else:visible['events_suppressed']=list(selected.values())
                    visible['events_attempted']=packet.get('events',[])
                    try:self.publisher.send(packet)
                    except Exception:
                        visible['delivery']='delivery_unknown'
                        with self.lock:self.state['windows'].append(visible)
                        raise
                    visible['delivery']='broker_accepted'
                    visible['events_sent']=packet.get('events',[])
                else:visible['delivery']='network_cut';visible['events_suppressed']=list(selected.values())
                with self.lock:
                    self.state['windows'].append(visible)
                    self.state['events'].extend(window.get('events',[]))
                    self.state['events'].extend({**e,'at_seconds':window['start_seconds']+e['at_seconds']} for e in visible['events_sent'] if e['origin']=='manual')
                    self.state['events'].extend({**e,'at_seconds':window['start_seconds']+e['at_seconds']} for e in visible.get('events_local',[]))
                    self.state['progress_seconds']=window['end_seconds']
                    self.state['elapsed_seconds']=window['end_seconds']
                    if visible['delivery']=='broker_accepted':self.state['broker_accepted']+=1
                    else:self.state['skipped_windows']+=1
            with self.lock:self.state['status']='stopped' if self.state['status']=='stopping' else 'completed'
        except Exception as error:
            with self.lock:
                self.state['status']='failed';self.state['error']=str(error) if isinstance(error,TransportUnavailable) else 'Exécution interrompue ; aucune réception en base n’est affirmée.'
        finally:
            self.publisher.close()
            with self.lock:
                self.state['cancelled_events']=list(self.pending_events);self.pending_events={};self.state['pending_events']=[]
                self.state['finished_at']=stamp();report=self.snapshot()
            try:
                self.output_dir.mkdir(parents=True,exist_ok=True)
                target=self.output_dir/(report['run_id']+'.json')
                target.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
                with self.lock:self.state['report_available']=True
            except (OSError,ValueError):
                with self.lock:self.state['report_available']=False;self.state['report_error']='Rapport local non enregistré.'

    def close(self):
        with self.lock:
            if self.state['status'] in ('running','paused'):self.state['status']='stopping';self.wake.set()
        if self.thread:self.thread.join(timeout=10)


def create_app(build=None,catalog_provider=None,publisher=None,output_dir=None):
    if build is None or catalog_provider is None:
        from engine import build_run,catalog
        build=build or build_run;catalog_provider=catalog_provider or catalog
    controller=Controller(build,publisher,output_dir);csrf=secrets.token_urlsafe(32)
    @asynccontextmanager
    async def lifespan(app):
        yield
        controller.close()
    app=FastAPI(title='Simulateur SKELIVIA local',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.controller=controller
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
    @app.middleware('http')
    async def local_boundary(request:Request,call_next):
        if request.method not in ('GET','HEAD'):
            if request.headers.get('origin') not in ('http://127.0.0.1:8774','http://localhost:8774','https://localhost:8443') or not secrets.compare_digest(request.headers.get('x-csrf-token',''),csrf):
                return JSONResponse({'detail':'Commande locale non autorisée.'},status_code=403)
            if request.headers.get('content-type','').split(';')[0]!='application/json':return JSONResponse({'detail':'JSON requis.'},status_code=415)
            if len(await request.body())>16384:return JSONResponse({'detail':'Requête trop volumineuse.'},status_code=413)
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer',
          'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self' https://wokwi.com; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        return response
    @app.get('/api/health')
    def health():return {'ok':True,'scope':'local_synthetic_simulator'}
    @app.get('/api/state')
    def state():return {'csrf_token':csrf,'state':controller.snapshot(),'transport':controller.publisher.status()}
    @app.get('/api/catalog')
    def get_catalog():return {**catalog_provider(),'transport':controller.publisher.status(),'fixed_target':'demo-device-a'}
    @app.get('/api/actions/catalog')
    def get_actions_catalog():
        from actions_catalog import catalog
        return catalog()
    @app.post('/api/events')
    def enqueue_event(body:EventRequest):return controller.enqueue_event(body.kind)
    @app.post('/api/preview')
    def preview(config:RunConfig):
        try:return controller.prepare(config.model_dump())
        except ValueError as error:raise HTTPException(422,str(error)) from None
    @app.post('/api/start')
    def start(config:RunConfig):return controller.start(config.model_dump())
    for action in ('pause','resume','stop'):
        def make_endpoint(name):
            def endpoint():return controller.control(name)
            return endpoint
        app.add_api_route('/api/'+action,make_endpoint(action),methods=['POST'])
    @app.get('/api/report')
    def report():
        value=controller.snapshot()
        if value['status'] not in ('completed','stopped','failed') or not value.get('run_id'):raise HTTPException(409,'Aucun rapport terminé.')
        return JSONResponse(value,headers={'Content-Disposition':'attachment; filename="skelivia-simulation-'+value['run_id']+'.json"'})
    @app.get('/brand/{name}')
    def brand(name:str):
        if name not in ('skelivia-logo-original.png','Orbitron.ttf'):raise HTTPException(404)
        folder=Path(os.getenv('SIMULATOR_BRAND_DIR',str(ROOT.parent/'application/app/static')))
        return FileResponse(folder/name)
    if (ROOT/'static').is_dir():app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
    @app.get('/')
    def index(request:Request):
        if os.getenv('SIMULATOR_PUBLIC_URL') and request.headers.get('x-forwarded-prefix')!='/simulateur':
            return RedirectResponse(os.environ['SIMULATOR_PUBLIC_URL'],status_code=307)
        return FileResponse(ROOT/'static/index.html')
    return app
