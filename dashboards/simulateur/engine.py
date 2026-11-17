"""Deterministic reference-derived simulator. No network, patient identity or wall clock."""
from __future__ import annotations
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path
import struct

DATA = Path(__file__).resolve().parent / 'source_data'
MODES = ('manual', 'normal', 'intensive', 'force', 'immobile', 'invalid', 'network_cut')
FLAGS = ('high_force', 'pause_reminder', 'quiet_contact', 'absent')
FAULT_SENSORS = ('all', 'thumb', 'palm', 'motion', 'contact')


def f(value):
    """IEEE binary32 rounding, as the reference ESP32/C++ float calculations."""
    return struct.unpack('f', struct.pack('f', value))[0]


def norm(x, y, z):
    return f(math.sqrt(f(f(f(x*x)+f(y*y))+f(z*z))))


def sample(**kw):
    return dict(ax=0., ay=0., az=f(9.80665), gx=0., gy=0., gz=0., thumb=1000,
                palm=1000, contact=True, motionValid=True, thumbValid=True,
                palmValid=True, contactValid=True) | kw


def preset(mode, elapsed, fault_sensor='all'):
    if mode == 'invalid' and fault_sensor != 'all':
        s = preset('normal', elapsed)
        s[{'thumb':'thumbValid', 'palm':'palmValid', 'motion':'motionValid', 'contact':'contactValid'}[fault_sensor]] = False
        return s
    s = sample()
    if mode == 'normal':
        s['contact'] = elapsed % 14000 < 8000
        s['ax'] = 4. if s['contact'] and elapsed % 1500 < 150 else 0.
        s['gz'] = .2 if s['contact'] and 100 <= elapsed % 1500 < 450 else 0.
        s['thumb'], s['palm'] = (1000, 1200) if s['contact'] else (0, 0)
    elif mode == 'intensive':
        s['ax'] = 5. if elapsed % 500 < 100 else 0.
        s['gz'] = .25 if 50 <= elapsed % 850 < 350 else 0.
    elif mode in ('force', 'network_cut'):
        s['ax'] = 4. if elapsed % 1500 < 150 else 0.
        s['gz'] = .2 if 100 <= elapsed % 1500 < 450 else 0.
        if mode == 'force': s['thumb'], s['palm'] = 3500, 3300
    elif mode == 'immobile':
        s['contact'] = elapsed % 24000 < 12000
        s['thumb'] = s['palm'] = 1000 if s['contact'] else 0
    elif mode == 'invalid':
        s.update(ax=float('nan'), gx=float('nan'), thumb=5000, palm=-1)
    return s


class Pipeline:
    """Port of source_data/pipeline.h gyro V2, including acceleration/continuity rules."""
    def __init__(self):
        self.total = self.accelerationTotal = self.contactMs = self.quietMs = 0
        self.absentMs = self.thumbHighMs = self.palmHighMs = 0
        self.lastEvent = self.accelerationLastEvent = self.lastTrigger = 0
        self.episodeStart = self.lastEpisodeStart = self.lastEpisodeDuration = 0
        self.lastEpisodePath = 0.
        self.hasTrigger = False
        self.stamps = []
        self.previousX = self.previousY = self.previousZ = 0.
        self.smoothGx = self.smoothGy = self.smoothGz = 0.
        self.invalidate_segment()

    def invalidate_segment(self):
        self.initialized = self.gyroInitialized = self.episodeActive = False
        self.filteredDelta = self.gyroNorm = self.previousGyroNorm = self.angularPath = 0.
        self.armed, self.gyroArmed = True, False
        self.stamps = []

    def update(self, raw, now, dt=50):
        s = raw.copy()
        for key in ('ax', 'ay', 'az', 'gx', 'gy', 'gz'): s[key] = f(s[key])
        if dt > 200:
            self.contactMs = self.quietMs = self.thumbHighMs = self.palmHighMs = self.absentMs = 0
            self.invalidate_segment(); dt = 0
        s['motionValid'] = s['motionValid'] and all(math.isfinite(s[k]) and abs(s[k]) < f(19.5) for k in ('ax','ay','az')) and all(math.isfinite(s[k]) and abs(s[k]) < f(4.35) for k in ('gx','gy','gz'))
        s['thumbValid'] = s['thumbValid'] and 0 <= s['thumb'] <= 4095
        s['palmValid'] = s['palmValid'] and 0 <= s['palm'] <= 4095
        self.last = s
        self.thumbPct = f(f(s['thumb']*100.) / f(4095.)) if s['thumbValid'] else None
        self.palmPct = f(f(s['palm']*100.) / f(4095.)) if s['palmValid'] else None
        self.movementEvent = False
        if s['motionValid']:
            if self.initialized:
                dx,dy,dz = f(s['ax']-self.previousX),f(s['ay']-self.previousY),f(s['az']-self.previousZ)
                self.filteredDelta = f(f(.5*self.filteredDelta)+f(.5*norm(dx,dy,dz)))
                if self.filteredDelta < f(.35): self.armed = True
                if self.armed and self.filteredDelta >= 1. and (self.accelerationTotal == 0 or now-self.accelerationLastEvent >= 250):
                    self.armed=False; self.accelerationLastEvent=now; self.accelerationTotal+=1
            self.previousX,self.previousY,self.previousZ = s['ax'],s['ay'],s['az']; self.initialized=True
            if not self.gyroInitialized:
                self.smoothGx,self.smoothGy,self.smoothGz=s['gx'],s['gy'],s['gz']
                self.gyroNorm=norm(self.smoothGx,self.smoothGy,self.smoothGz)
                self.gyroArmed=self.gyroNorm < f(.025); self.gyroInitialized=True
            else:
                self.smoothGx=f(self.smoothGx+f(f(.2)*f(s['gx']-self.smoothGx)))
                self.smoothGy=f(self.smoothGy+f(f(.2)*f(s['gy']-self.smoothGy)))
                self.smoothGz=f(self.smoothGz+f(f(.2)*f(s['gz']-self.smoothGz)))
                self.gyroNorm=norm(self.smoothGx,self.smoothGy,self.smoothGz)
                if self.episodeActive: self.angularPath=f(self.angularPath+f(self.previousGyroNorm*f(dt/1000.)))
                if self.gyroNorm < f(.025):
                    self.gyroArmed=True
                    if self.episodeActive:
                        duration=now-self.episodeStart
                        if duration >= 500 and f(self.angularPath+f(1e-6)) >= f(.05):
                            self.movementEvent=True; self.total+=1; self.lastEvent=now
                            self.lastEpisodeStart,self.lastEpisodeDuration,self.lastEpisodePath=self.episodeStart,duration,self.angularPath
                            self.stamps=(self.stamps+[now])[-64:]
                        self.episodeActive=False
                if not self.episodeActive and self.gyroArmed and self.gyroNorm >= f(.05) and (not self.hasTrigger or now-self.lastTrigger >= 400):
                    self.episodeActive=True; self.episodeStart=now; self.angularPath=0.
                    self.gyroArmed=False; self.hasTrigger=True; self.lastTrigger=now
            self.previousGyroNorm=self.gyroNorm
        else: self.invalidate_segment()
        if s['contactValid'] and s['contact']:
            self.absentMs=0; self.contactMs+=dt
            moving=self.episodeActive or self.movementEvent or self.gyroNorm >= f(.025) or self.filteredDelta >= 1.
            self.quietMs=0 if moving or not s['motionValid'] else self.quietMs+dt
        else:
            self.quietMs=0
            if s['contactValid']:
                self.absentMs+=dt
                if self.absentMs>=3000:self.contactMs=0
            else:self.absentMs=self.contactMs=0
        ok=s['contactValid'] and s['contact']
        self.thumbHighMs=self.thumbHighMs+dt if ok and s['thumbValid'] and self.thumbPct>=70 else 0
        self.palmHighMs=self.palmHighMs+dt if ok and s['palmValid'] and self.palmPct>=70 else 0
        self.flags={'high_force':self.thumbHighMs>=5000 or self.palmHighMs>=5000,
                    'pause_reminder':ok and s['motionValid'] and self.contactMs>=20000 and sum(now-t<10000 for t in self.stamps)>=10,
                    'quiet_contact':ok and s['motionValid'] and self.quietMs>=10000,
                    'absent':s['contactValid'] and not s['contact'] and self.absentMs>=3000}
        return self


def _manifest():
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['files']:
        if hashlib.sha256((DATA/entry['file']).read_bytes()).hexdigest()!=entry['sha256']:
            raise ValueError('Reference hash mismatch: '+entry['file'])
    return manifest


def catalog():
    m=_manifest()
    return {'sources':['wokwi','phyphox'],'modes':list(MODES),'fault_sensors':list(FAULT_SENSORS),'datasets':m['datasets'],
            'duration_seconds':{'min':5,'max':300,'multiple':5,'default':30},'step_ms':50,
            'window_seconds':5,'manual_defaults':{k:v for k,v in sample().items() if not k.endswith('Valid')},
            'balance_reference':m['balance_reference'],
            'limitations':['Demonstration thresholds, not clinical thresholds.',
                            'Phyphox measures motion only; FSR/contact require explicitly synthetic assumptions.']}


def _parameters(value, assumptions=False):
    if not isinstance(value,dict):raise ValueError('Parameters must be an object')
    allowed={'thumb','palm','contact'} if assumptions else {'ax','ay','az','gx','gy','gz','thumb','palm','contact'}
    if set(value)-allowed:raise ValueError('Unknown manual field')
    if assumptions and set(value)!=allowed:raise ValueError('Replay assumptions require thumb, palm and contact')
    for k,v in value.items():
        if k=='contact':
            if type(v) is not bool:raise ValueError('Contact must be boolean')
        elif k in ('thumb','palm'):
            if type(v) is not int or not 0<=v<=4095:raise ValueError('ADC must be an integer in 0..4095')
        elif type(v) not in (int,float) or not math.isfinite(v) or abs(v)>100:
            raise ValueError('Motion axes must be finite and bounded')
    return value


def _read_axes(filename, columns):
    values=[]
    with (DATA/filename).open(encoding='utf-8-sig',newline='') as stream:
        for row in csv.DictReader(stream):
            t=float(row['time_s'])
            if not math.isfinite(t) or (values and t<=values[-1][0]):raise ValueError('Reference time must be finite and strictly increasing')
            axes=tuple(float(row[c]) if row[c].strip() else float('nan') for c in columns)
            values.append((t,axes))
    if not values:raise ValueError('Empty reference')
    return values


def _aligned(axes, times, t):
    i=bisect.bisect_left(times,t)
    if i<len(times) and abs(times[i]-t)<1e-9:return axes[i][1]
    if i==0 or i==len(times) or times[i]-times[i-1]>.2:return None
    ratio=(t-times[i-1])/(times[i]-times[i-1])
    return tuple(a+(b-a)*ratio for a,b in zip(axes[i-1][1],axes[i][1]))


def _replay(dataset, duration, assumptions):
    gyro=_read_axes(dataset['gyro'],('gx_rad_s','gy_rad_s','gz_rad_s'))
    accel=_read_axes(dataset['accel'],('ax_m_s2','ay_m_s2','az_m_s2'));times=[r[0] for r in accel]
    origin=gyro[0][0];previous=0.
    for absolute,g in gyro:
        t=absolute-origin
        a=_aligned(accel,times,absolute)
        s=sample(gx=g[0],gy=g[1],gz=g[2],motionValid=a is not None,
                 contactValid=assumptions is not None,thumbValid=assumptions is not None,palmValid=assumptions is not None)
        if a:s.update(ax=a[0],ay=a[1],az=a[2])
        if assumptions:s.update(assumptions)
        yield t,previous,min(t,duration),s,absolute
        previous=t
        if t>=duration:break


def build_run(config):
    """Pure bounded execution; windows are never published by this function."""
    if not isinstance(config,dict):raise ValueError('Configuration must be an object')
    allowed={'source','mode','duration_seconds','step_ms','dataset_id','manual','replay_assumptions','include_samples','fault_sensor'}
    if set(config)-allowed:raise ValueError('Unknown configuration field')
    source=config.get('source','wokwi');mode=config.get('mode','normal');duration=config.get('duration_seconds',30)
    if source not in ('wokwi','phyphox') or mode not in MODES:raise ValueError('Unknown source/mode')
    fault_sensor=config.get('fault_sensor','all')
    if fault_sensor not in FAULT_SENSORS:raise ValueError('Unknown fault sensor')
    if fault_sensor!='all' and (source!='wokwi' or mode!='invalid'):raise ValueError('Targeted faults require the Wokwi invalid scenario')
    faults=(['thumb','palm','motion'] if fault_sensor=='all' else [fault_sensor]) if source=='wokwi' and mode=='invalid' else []
    if type(duration) is not int or not 5<=duration<=300 or duration%5:raise ValueError('Duration must be 5..300 seconds in multiples of five')
    if type(config.get('step_ms',50)) is not int or config.get('step_ms',50)!=50:raise ValueError('Wokwi reference uses fixed 50 ms sampling')
    if type(config.get('include_samples',False)) is not bool:raise ValueError('include_samples must be boolean')
    manual=_parameters(config.get('manual',{}));assumptions=config.get('replay_assumptions')
    if assumptions is not None:assumptions=_parameters(assumptions,True)
    manifest=_manifest();dataset=None
    if source=='phyphox':
        dataset=next((d for d in manifest['datasets'] if d['id']==config.get('dataset_id','usage')),None)
        if dataset is None:raise ValueError('Unknown reference dataset')
        entries=_replay(dataset,duration,assumptions)
    else:
        entries=((t/1000,t/1000,(t+50)/1000,sample(**manual) if mode=='manual' else preset(mode,t,fault_sensor),None) for t in range(0,duration*1000,50))
    accum=[{'coverage':0.,'valid':0.,'contact':0.,'thumb':0.,'palm':0.,'episodes':0,'events':[]} for _ in range(duration//5)]
    p=Pipeline();samples=[];events=[];previous_ms=0;flags={k:False for k in FLAGS};count=0;gaps=0;last_t=0.
    for t,start,end,s,absolute in entries:
        now_ms=round(t*1000);dt=50 if source=='wokwi' else now_ms-previous_ms;previous_ms=now_ms
        if source=='phyphox' and t-start>.2+1e-9:dt=max(dt,201)
        p.update(s,now_ms,dt);count+=1;last_t=t
        valid=all(p.last[k] for k in ('motionValid','thumbValid','palmValid','contactValid')) and 0<=t-start<=.2+1e-9
        # Wokwi time labels start each sample's [t,t+50ms) interval.
        if source=='wokwi':valid=all(p.last[k] for k in ('motionValid','thumbValid','palmValid','contactValid'))
        gap=source=='phyphox' and t-start>.2+1e-9
        if gap:gaps+=1
        for i,b in enumerate(accum):
            overlap=max(0.,min(end,(i+1)*5)-max(start,i*5))
            if not overlap:continue
            if not gap:b['coverage']+=overlap
            if valid:
                b['valid']+=overlap;b['contact']+=overlap if p.last['contact'] else 0.
                b['thumb']+=p.thumbPct*overlap;b['palm']+=p.palmPct*overlap
        current=[]
        if p.movementEvent:current.append({'kind':'gyro_episode','at_seconds':t,'start_seconds':p.lastEpisodeStart/1000,'duration_seconds':p.lastEpisodeDuration/1000,'angular_path_rad':p.lastEpisodePath})
        for flag in FLAGS:
            if p.flags[flag] and not flags[flag]:current.append({'kind':flag,'at_seconds':t})
        flags=p.flags.copy()
        for event in current:
            if 0<=t<duration:
                events.append(event);b=accum[int(t//5)];b['events'].append(event)
                if event['kind']=='gyro_episode':b['episodes']+=1
        if config.get('include_samples') and t<duration:
            clean={k:(None if isinstance(v,float) and not math.isfinite(v) else v) for k,v in p.last.items()}
            samples.append({'time_seconds':t,'source_time_seconds':absolute,'dt_seconds':.05 if source=='wokwi' else t-start,'sample':clean,'gyro_norm':p.gyroNorm,'thumb_pct':p.thumbPct,'palm_pct':p.palmPct,'valid':valid,'gyro_episodes_total':p.total,'acceleration_events_total':p.accelerationTotal,'flags':p.flags.copy(),'synthetic':True})
            samples[-1].update(fault_sensors=faults.copy(),
                contact_seconds=p.contactMs/1000 if p.last['contactValid'] and not gap else None,
                quiet_seconds=p.quietMs/1000 if p.last['contactValid'] and p.last['motionValid'] and not gap else None,
                motion_active=bool(p.episodeActive or p.movementEvent or p.gyroNorm>=f(.025) or p.filteredDelta>=1.) if p.last['motionValid'] and not gap else None)
    windows=[]
    for i,b in enumerate(accum):
        valid=abs(b['coverage']-5)<1e-6 and abs(b['valid']-5)<1e-6
        metrics={'contact_seconds':round(b['contact'],9),'episodes':b['episodes'],'thumb_pct':b['thumb']/5,'palm_pct':b['palm']/5} if valid else dict.fromkeys(('contact_seconds','episodes','thumb_pct','palm_pct'))
        windows.append({'index':i,'start_seconds':i*5,'end_seconds':(i+1)*5,'duration_seconds':5,'quality':'valid' if valid else 'invalid','metrics':metrics,'events':b['events'],'publish':not(source=='wokwi' and mode=='network_cut'),'synthetic':True,'valid_seconds':round(b['valid'],9),'missing_seconds':round(max(0.,5-b['coverage']),9)})
    if source=='wokwi' and mode=='network_cut':events.append({'kind':'network_cut','at_seconds':0,'until_seconds':duration})
    if faults:events.append({'kind':'sensor_fault','at_seconds':0,'sensors':faults.copy(),'origin':'computed'})
    events.sort(key=lambda event:event['at_seconds'])
    selected={'pipeline.h','appuis_balance.csv'} | ({dataset['gyro'],dataset['accel']} if dataset else set())
    provenance={'source':source,'mode':mode if source=='wokwi' else 'native_timestamp_replay','dataset_id':dataset['id'] if dataset else None,'files':[v for v in manifest['files'] if v['file'] in selected],'synthetic':True,'manual':({k:v for k,v in sample(**manual).items() if not k.endswith('Valid')} if source=='wokwi' and mode=='manual' else None),'replay_assumptions':assumptions if source=='phyphox' else None,'balance_reference':manifest['balance_reference'],'rules':'pipeline.h gyro V2 release confirmation; thresholds demonstrator only','alignment':'native gyro timestamps; linear accel interpolation only between neighbors <=0.2s; no extrapolation'}
    result={'windows':windows,'summary':{'synthetic':True,'duration_seconds':duration,'samples_processed':count,'valid_windows':sum(w['quality']=='valid' for w in windows),'invalid_windows':sum(w['quality']=='invalid' for w in windows),'gyro_episodes_confirmed':sum(e['kind']=='gyro_episode' for e in events),'acceleration_events_secondary':p.accelerationTotal,'acquisition_gaps':gaps,'publishable_windows':sum(w['publish'] for w in windows)},'provenance':provenance,'events_expected':events}
    provenance['fault_sensor']=fault_sensor if faults else None
    if config.get('include_samples'):result['samples']=samples
    return result
