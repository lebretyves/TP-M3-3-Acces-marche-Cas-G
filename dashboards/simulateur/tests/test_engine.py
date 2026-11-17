import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simulator_engine',ROOT/'engine.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)


def test_determinism_valid_intervals_and_no_cumulative_counter():
    cfg={'mode':'intensive','duration_seconds':30,'include_samples':True}
    run=engine.build_run(cfg)
    assert run==engine.build_run(cfg)
    assert len(run['windows'])==6
    assert all(w['quality']=='valid' and w['metrics']['contact_seconds']==5 for w in run['windows'])
    assert sum(w['metrics']['episodes'] for w in run['windows'])==run['summary']['gyro_episodes_confirmed']
    assert run['windows'][0]['end_seconds']==run['windows'][1]['start_seconds']
    assert any(e['kind']=='pause_reminder' for e in run['events_expected'])
    assert run['summary']['gyro_episodes_confirmed']>20
    json.dumps(run,allow_nan=False)


def test_normal_pressure_weighted_by_actual_contact_durations():
    run=engine.build_run({'mode':'normal','duration_seconds':15})
    a,b,c=run['windows']
    assert [w['metrics']['contact_seconds'] for w in (a,b,c)]==[5,3,1]
    assert b['metrics']['thumb_pct']==pytest.approx((1000*100/4095)*3/5,abs=1e-5)
    assert not any(e['kind'] in ('high_force','pause_reminder') for e in run['events_expected'])


def test_invalid_missing_metrics_and_network_cut_keeps_local_acquisition():
    bad=engine.build_run({'mode':'invalid','duration_seconds':10,'include_samples':True})
    assert all(w['quality']=='invalid' and all(v is None for v in w['metrics'].values()) for w in bad['windows'])
    json.dumps(bad,allow_nan=False)
    cut=engine.build_run({'mode':'network_cut','duration_seconds':10})
    assert all(not w['publish'] and w['quality']=='valid' for w in cut['windows'])
    assert cut['summary']['gyro_episodes_confirmed']>0
    assert any(e['kind']=='network_cut' for e in cut['events_expected'])


def test_demonstrator_events_and_manual_no_false_motion():
    force=engine.build_run({'mode':'force','duration_seconds':10})
    assert any(e['kind']=='high_force' for e in force['events_expected'])
    quiet=engine.build_run({'mode':'immobile','duration_seconds':20})
    assert {e['kind'] for e in quiet['events_expected']}=={'quiet_contact','absent'}
    manual=engine.build_run({'mode':'manual','manual':{'thumb':0,'palm':0,'contact':False},'duration_seconds':5})
    assert manual['windows'][0]['metrics']=={'contact_seconds':0.,'episodes':0,'thumb_pct':0.,'palm_pct':0.}


def test_native_replay_missing_contact_and_explicit_assumptions():
    unmeasured=engine.build_run({'source':'phyphox','dataset_id':'usage','duration_seconds':10,'include_samples':True})
    assert all(w['quality']=='invalid' for w in unmeasured['windows'])
    assert unmeasured['provenance']['replay_assumptions'] is None
    times=[s['source_time_seconds'] for s in unmeasured['samples']]
    assert times[0]==pytest.approx(.010050305)
    assert times[1]-times[0]!=pytest.approx(.05)
    assert len(set(round(s['dt_seconds'],9) for s in unmeasured['samples']))>10
    assumed=engine.build_run({'source':'phyphox','dataset_id':'usage','duration_seconds':10,'replay_assumptions':{'thumb':1000,'palm':1200,'contact':True}})
    assert assumed['summary']['valid_windows']>=1
    assert assumed['provenance']['replay_assumptions']['contact'] is True
    assert assumed['provenance']['synthetic']
    assert assumed['provenance']['balance_reference']['thumb_g']==[189,361,344]
    json.dumps(unmeasured,allow_nan=False)


def test_alignment_no_extrapolation_or_long_gap():
    values=[(0.,(0.,0.,0.)),(.1,(1.,2.,3.)),(.5,(4.,5.,6.))]
    times=[x[0] for x in values]
    assert engine._aligned(values,times,.05)==(.5,1.,1.5)
    assert engine._aligned(values,times,.3) is None
    assert engine._aligned(values,times,-.01) is None
    assert engine._aligned(values,times,.6) is None


def test_gyro_confirmed_on_release_gap_cannot_confirm():
    p=engine.Pipeline();p.update(engine.sample(),0,0)
    for t in range(50,1050,50):p.update(engine.sample(gz=.2),t)
    assert p.total==0 and p.episodeActive
    for t in range(1050,1850,50):p.update(engine.sample(),t)
    assert p.total==1 and p.accelerationTotal==0
    p=engine.Pipeline();p.update(engine.sample(),0,0)
    for t in range(50,1050,50):p.update(engine.sample(gz=.2),t)
    p.update(engine.sample(gz=.2),1600,600)
    for t in range(1650,2550,50):p.update(engine.sample(),t)
    assert p.total==0


@pytest.mark.parametrize('cfg',[{'duration_seconds':0},{'duration_seconds':301},{'duration_seconds':True},{'step_ms':20},{'patient_id':'p-alice'},{'mode':'fake'},{'manual':{'thumb':5000}},{'manual':{'contact':1}},{'manual':{'gx':float('nan')}},{'replay_assumptions':{'contact':True}},{'source':'phyphox','dataset_id':'../../secret'}])
def test_strict_bounded_config(cfg):
    with pytest.raises(ValueError):engine.build_run(cfg)


def test_reference_hash_verification_and_catalog():
    cat=engine.catalog()
    assert cat['modes']==list(engine.MODES)
    assert len(cat['datasets'])==3
    assert 'motionValid' not in cat['manual_defaults']
    assert len(engine._manifest()['files'])==8


def test_reference_modification_is_rejected(tmp_path,monkeypatch):
    (tmp_path/'changed.csv').write_text('changed',encoding='utf-8')
    (tmp_path/'manifest.json').write_text(json.dumps({'files':[{'file':'changed.csv','sha256':'0'*64}]}),encoding='utf-8')
    monkeypatch.setattr(engine,'DATA',tmp_path)
    with pytest.raises(ValueError,match='hash mismatch'):engine._manifest()


def test_replay_gap_not_integrated_and_variable_dt_weighting(monkeypatch):
    def replay(dataset,duration,assumptions):
        previous=0.
        # Irregular but continuous acquisition, changing ADC halfway through 5s.
        times=[i*.1 for i in range(1,26)]+[2.5+i*.05 for i in range(1,51)]
        for t in times:
            yield t,previous,t,engine.sample(thumb=1000 if t<=2.5 else 3000),100+t
            previous=t
    monkeypatch.setattr(engine,'_replay',replay)
    run=engine.build_run({'source':'phyphox','duration_seconds':5})
    assert run['windows'][0]['quality']=='valid'
    assert run['windows'][0]['metrics']['thumb_pct']==pytest.approx(2000*100/4095,abs=1e-5)
    def replay_gap(dataset,duration,assumptions):
        previous=0.
        for i in range(1,51):
            t=i*.1
            if 1<t<2:continue
            yield t,previous,t,engine.sample(gz=.2 if t<2 else 0),100+t
            previous=t
    monkeypatch.setattr(engine,'_replay',replay_gap)
    run=engine.build_run({'source':'phyphox','duration_seconds':5})
    assert run['summary']['acquisition_gaps']==1
    assert run['windows'][0]['missing_seconds']==1
    assert run['windows'][0]['quality']=='invalid'
    assert all(v is None for v in run['windows'][0]['metrics'].values())
    assert run['summary']['gyro_episodes_confirmed']==0


def test_cpp_equivalence_all_seven_modes(tmp_path):
    """Compile the exact hashed reference, compare every tick, not a rewritten oracle."""
    vc=Path('C:/Program Files/Microsoft Visual Studio/18/Insiders/VC/Auxiliary/Build/vcvars64.bat')
    compiler=shutil.which('clang++') or shutil.which('g++')
    if not compiler and not (sys.platform=='win32' and vc.exists()):pytest.skip('No local C++ compiler available')
    source=tmp_path/'reference.cpp';exe=tmp_path/('reference.exe' if sys.platform=='win32' else 'reference')
    source.write_text('#include "'+(ROOT/'source_data/pipeline.h').as_posix()+'"\n#include <cstdio>\nint main(){if(!pipelineSelfTest())return 9; for(int mode=0;mode<7;mode++){Pipeline p;for(unsigned t=0;t<30000;t+=50){p.update(presetSample(mode,t),t,50);std::printf("%d %u %u %u %d %d %d %d %.9g %.9g %.9g\\n",mode,t,p.total,p.accelerationTotal,p.highForce,p.pauseReminder,p.quietContact,p.absent,p.gyroNorm,p.angularPath,p.thumbPct);}}}\n',encoding='utf-8')
    if compiler:cmd=[compiler,'-std=c++17','-O0',str(source),'-o',str(exe)]
    else:
        bat=tmp_path/'build.cmd'
        bat.write_text('@echo off\ncall "'+str(vc)+'" >nul\nif errorlevel 1 exit /b 1\ncl /nologo /EHsc /std:c++17 /Od /fp:strict /Fe:"'+str(exe)+'" /Fo:"'+str(tmp_path/'reference.obj')+'" "'+str(source)+'"\nexit /b %errorlevel%\n',encoding='utf-8')
        cmd=['cmd','/d','/c',str(bat)]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    pipelines=[engine.Pipeline() for _ in engine.MODES]
    lines=result.stdout.strip().splitlines();assert len(lines)==4200
    for line in lines:
        values=line.split();mode,t=map(int,values[:2]);p=pipelines[mode].update(engine.preset(engine.MODES[mode],t),t)
        assert [p.total,p.accelerationTotal,*[int(p.flags[k]) for k in engine.FLAGS]]==list(map(int,values[2:8])),line
        assert p.gyroNorm==pytest.approx(float(values[8]),abs=1e-7),line
        assert p.angularPath==pytest.approx(float(values[9]),abs=1e-7),line
        if p.thumbPct is None:assert math.isnan(float(values[10]))
        else:assert p.thumbPct==pytest.approx(float(values[10]),abs=1e-6),line
