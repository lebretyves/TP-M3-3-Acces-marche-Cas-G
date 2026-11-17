"""FHIR R4 test-bank adapter. No clinical endpoint or CI-SIS conformity claimed."""
from datetime import date,datetime,timezone
import math
from uuid import uuid5,NAMESPACE_URL
from fastapi import Depends,HTTPException
from fastapi.responses import JSONResponse
from .database import configure_actor
from .domain import export_measure_rows,audit

METRICS={'contact_seconds':('contact-duration','s','s'),'episodes':('movement-episodes','episode','1'),'thumb_pct':('relative-thumb-pressure','%','%'),'palm_pct':('relative-palm-pressure','%','%')}
TAG={'system':'urn:skelivia:data-origin','code':'synthetic-test','display':'Synthetic test data; not clinically validated'}


def make_bundle(patient_id,measurements):
    patient_uuid=str(uuid5(NAMESPACE_URL,'skelivia-patient:'+patient_id))
    reference='urn:uuid:'+patient_uuid
    entries=[{'fullUrl':reference,'resource':{'resourceType':'Patient','id':patient_uuid,'meta':{'tag':[TAG]},'identifier':[{'system':'urn:skelivia:synthetic-patient','value':patient_id}]}}]
    for row in measurements:
        if row.get('patient_id')!=patient_id or row.get('synthetic') is not True:
            raise ValueError('Only the requested synthetic patient is permitted.')
        observed=datetime.fromisoformat(row['recorded_at'].replace('Z','+00:00'))
        if observed.tzinfo is None:raise ValueError('Measurement time must be timezone-aware.')
        for key,(code,unit,ucum) in METRICS.items():
            if key not in row['metrics']:continue
            ident=str(uuid5(NAMESPACE_URL,'skelivia-observation:'+row['id']+':'+key))
            value=row['metrics'][key]
            resource={'resourceType':'Observation','id':ident,'meta':{'tag':[TAG]},'status':'preliminary','code':{'coding':[{'system':'urn:skelivia:measurements:v1','code':code}]},'subject':{'reference':reference},'effectiveDateTime':row['recorded_at'],'note':[{'text':'Données du banc synthétique. Appuis relatifs, sans conversion en force ni diagnostic. Calibration : '+str(row.get('calibration','unknown'))}]}
            if row['quality']!='valid' or value is None:
                resource['dataAbsentReason']={'coding':[{'system':'http://terminology.hl7.org/CodeSystem/data-absent-reason','code':'error'}]}
            else:
                if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0 or (key.endswith('_pct') and value>100):raise ValueError('Invalid metric or unit.')
                resource['valueQuantity']={'value':value,'unit':unit,'system':'http://unitsofmeasure.org','code':ucum}
            entries.append({'fullUrl':'urn:uuid:'+ident,'resource':resource})
    return {'resourceType':'Bundle','type':'collection','meta':{'tag':[TAG]},'timestamp':datetime.now(timezone.utc).isoformat(),'entry':entries}


def install_fhir(app,factory,account_dep):
    @app.get('/api/fhir/export')
    def export(start:date,end:date,a=Depends(account_dep)):
        if a.role!='user':raise HTTPException(404,'Export indisponible.')
        if end<start or (end-start).days>90:raise HTTPException(422,'Période de 90 jours maximum.')
        with factory() as db:
            configure_actor(db,a)
            rows=export_measure_rows(db,a,start.isoformat(),end.isoformat(),cap=1000)
            try: bundle=make_bundle(a.patient_id,rows)
            except ValueError:raise HTTPException(409,'Données incompatibles avec le contrat synthétique FHIR.') from None
            audit(db,a,'fhir.synthetic.export',a.patient_id);db.commit()
        return JSONResponse(bundle,media_type='application/fhir+json',headers={'Content-Disposition':'attachment; filename="skelivia-fhir-test.json"'})
