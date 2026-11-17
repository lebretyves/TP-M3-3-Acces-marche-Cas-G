/* Counts for the displayed run only. Planned totals never become observations. */
(()=>{'use strict';
const count=value=>Number.isInteger(value)&&value>=0?value:null;
const empty=()=>({total:null,valid:null,invalid:null,sent:null,unsent:null,unknown:null,gyro:null,calibration:null});
function summarize(view,data){
  const expected=empty(),observed=empty();
  if(!data||!['live','preview'].includes(view))return {expected,observed};
  const summary=data.summary||{},config=data.config||data.provenance||{};
  expected.valid=count(summary.valid_windows);
  expected.invalid=count(summary.invalid_windows);
  expected.total=expected.valid!==null&&expected.invalid!==null?expected.valid+expected.invalid:null;
  expected.sent=config.delivery_mode==='local'||(config.source==='wokwi'&&config.mode==='network_cut')?0:count(summary.publishable_windows);
  expected.gyro=count(summary.gyro_episodes_confirmed);
  if(view!=='live')return {expected,observed};
  if(Array.isArray(data.windows)){
    const windows=data.windows;
    observed.total=windows.length;
    const qualitiesKnown=windows.every(w=>['valid','invalid','calibration_required'].includes(w.quality));
    if(qualitiesKnown){
      observed.valid=windows.filter(w=>w.quality==='valid').length;
      observed.invalid=windows.filter(w=>['invalid','calibration_required'].includes(w.quality)).length;
      observed.calibration=windows.filter(w=>w.quality==='calibration_required').length;
    }
    observed.sent=windows.filter(w=>w.delivery==='broker_accepted').length;
    observed.unsent=windows.filter(w=>['local_only','network_cut'].includes(w.delivery)).length;
    observed.unknown=windows.filter(w=>!['broker_accepted','local_only','network_cut'].includes(w.delivery)).length;
  }
  if(Array.isArray(data.detected_events)&&Number.isFinite(data.elapsed_seconds)){
    const events=data.detected_events.filter(e=>e.kind==='gyro_episode');
    if(events.every(e=>Number.isFinite(e.at_seconds)))observed.gyro=events.filter(e=>e.at_seconds<data.elapsed_seconds).length;
  }
  return {expected,observed};
}
if(typeof module!=='undefined'&&module.exports)module.exports={summarize};
if(typeof window!=='undefined')window.SkeliviaStats={summarize};
})();
