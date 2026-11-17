"""Bounded presentation of existing engine samples; no sensor model in the UI."""
import math

MAX_POINTS=6000


def chart_samples(samples):
    stride=max(1,math.ceil(len(samples)/MAX_POINTS))
    points=[]
    for index in range(0,len(samples),stride):
        row=samples[index];sample=row.get('sample',{})
        segment=samples[max(0,index-stride+1):index+1]
        # Never interpolate across a hole that fell between retained samples.
        gap=any(not 0<=item.get('dt_seconds',0)<=.2+1e-9 for item in segment)
        def available(channel):
            return not gap and all(item.get('sample',{}).get(channel) for item in segment)
        def number(value,valid):
            return float(value) if valid and isinstance(value,(int,float)) and math.isfinite(value) else None
        values={
            'thumb':number(row.get('thumb_pct'),available('thumbValid')),
            'palm':number(row.get('palm_pct'),available('palmValid')),
            'motion':number(row.get('gyro_norm'),available('motionValid')),
            'contact':bool(sample['contact']) if available('contactValid') else None,
        }
        # Only an explicit injected fault is red. Missing replay channels and gaps
        # stay unknown even when the aggregate window is invalid.
        faults=set(row.get('fault_sensors',[]))
        motion_active=row.get('motion_active') if available('motionValid') else None
        states={}
        for sensor,value in values.items():
            if sensor in faults and not gap:states[sensor]='fault'
            elif value is None:states[sensor]='unknown'
            elif sensor in ('thumb','palm'):
                states[sensor]='high' if value>=70 else 'active' if value>0 else 'rest'
            elif sensor=='motion':
                states[sensor]='active' if motion_active is True else 'rest' if motion_active is False else 'unknown'
            else:states[sensor]='active' if value else 'rest'
        points.append({
            'time_seconds':float(row['time_seconds']),
            'thumb_pct':number(row.get('thumb_pct'),available('thumbValid')),
            'palm_pct':number(row.get('palm_pct'),available('palmValid')),
            'gyro_norm':number(row.get('gyro_norm'),available('motionValid')),
            'contact':bool(sample['contact']) if available('contactValid') else None,
            'valid':not gap and all(item.get('valid') is True for item in segment),
            'gyro_episodes_total':row.get('gyro_episodes_total',0),
            'sensor_states':states,
            'motion_active':motion_active,
            'contact_seconds':number(row.get('contact_seconds'),available('contactValid')),
            'quiet_seconds':number(row.get('quiet_seconds'),available('contactValid') and available('motionValid')),
            'flags':{kind:row.get('flags',{}).get(kind) is True and not gap for kind in ('pause_reminder','high_force','quiet_contact','absent')},
        })
    return points
