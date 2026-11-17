"""Read only the fixed synthetic device's technical metadata via an offline operator.

No database credential, account profile, report or health measurement is copied
to the simulator. This script never changes calibration or device ownership.
"""
import argparse
from datetime import datetime,timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time
from uuid import UUID

ROOT=Path(__file__).resolve().parent
APPLICATION=ROOT.parent/'application'
DEVICE_ID='demo-device-a'
CERT_CN='skm-001'

READ_TECHNICAL="""import json,time
from datetime import datetime,timezone
from app.database import database
from app.domain_models import DomainRecord
from app.transport_models import DeviceIdentity,IngestDeviceCursor
engine,sessions=database()
with sessions() as db:
 device=db.get(DomainRecord,'demo-device-a');identity=db.get(DeviceIdentity,'skm-001')
 if not device or device.kind!='device' or device.owner_id!='u-alice' or device.patient_id!='p-alice':raise RuntimeError('Fixed synthetic device binding unavailable')
 if not identity or identity.device_id!=device.id:raise RuntimeError('Certificate registry mismatch')
 data=device.data;certificate=data.get('certificate',{})
 if certificate.get('serial')!=identity.cert_serial:raise RuntimeError('Certificate serial mismatch')
 cursor=db.get(IngestDeviceCursor,device.id)
 print(json.dumps({'device_id':device.id,'cert_cn':identity.cert_cn,'calibration_version':data.get('calibration'),'firmware_version':data.get('firmware'),'algorithm_version':'gyro-v2-simulator','calibration_status':data.get('calibration_status'),'technical_runtime':{'prepared_at':datetime.now(timezone.utc).isoformat(),'synthetic':True,'source':'fixed_device_registry','device_status':device.status,'certificate_revoked':bool(identity.revoked_at is not None or certificate.get('revoked')),'certificate_expires_at':identity.expires_at,'last_window_end':cursor.last_window_end if cursor else None}}))
engine.dispose()
"""

READ_RECEIPT="""import json,sys
from datetime import datetime,timezone
from uuid import UUID
from sqlalchemy import select
from app.database import database
from app.models import Report
from app.transport_models import IngestReceipt
run=str(UUID(sys.argv[1]))
engine,sessions=database()
with sessions() as db:
 rows=db.execute(select(IngestReceipt.sequence,IngestReceipt.report_id,Report.quality,Report.synthetic,(Report.patient_id=='p-alice').label('fixed_patient')).join(Report,Report.id==IngestReceipt.report_id).where(IngestReceipt.device_id=='demo-device-a',IngestReceipt.session_id==run).order_by(IngestReceipt.sequence)).all()
 if len(rows)>60:raise RuntimeError('Unexpected simulator receipt count')
 print(json.dumps({'run_id':run,'device_id':'demo-device-a','verified_at':datetime.now(timezone.utc).isoformat(),'database_receipts':len(rows),'all_synthetic':all(row.synthetic for row in rows),'fixed_patient_binding':all(row.fixed_patient for row in rows),'reports':[{'sequence':row.sequence,'report_id':row.report_id,'quality':row.quality} for row in rows]}))
engine.dispose()
"""


def validate_metadata(data,now=None):
    now=time.time() if now is None else now
    required={'device_id','cert_cn','calibration_version','firmware_version','algorithm_version','calibration_status','technical_runtime'}
    if not isinstance(data,dict) or set(data)!=required:raise ValueError('Unexpected transport metadata')
    if data['device_id']!=DEVICE_ID or data['cert_cn']!=CERT_CN:raise ValueError('Only the fixed synthetic device is allowed')
    if data['algorithm_version']!='gyro-v2-simulator':raise ValueError('Unexpected algorithm identity')
    for field in ('calibration_version','firmware_version'):
        if not isinstance(data[field],str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',data[field]):raise ValueError('Missing or invalid technical version')
    runtime=data['technical_runtime']
    allowed={'prepared_at','synthetic','source','device_status','certificate_revoked','certificate_expires_at','last_window_end'}
    if not isinstance(runtime,dict) or set(runtime)!=allowed or runtime['synthetic'] is not True:raise ValueError('Unexpected runtime metadata')
    if runtime['certificate_revoked'] is not False:raise ValueError('Revoked certificate refused')
    expires=runtime['certificate_expires_at']
    if not isinstance(expires,(int,float)) or isinstance(expires,bool) or not math.isfinite(expires) or expires<=now:raise ValueError('Expired or unknown certificate refused')
    if runtime['device_status'] in ('revoked','retired','deleted','lost','replaced'):raise ValueError('Inactive device refused')
    if not isinstance(data['calibration_status'],str) or not 1<=len(data['calibration_status'])<=40:raise ValueError('Calibration state unavailable')
    return data


def private_runtime(operator_account=None):
    runtime=ROOT/'.runtime';runtime.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        identity=subprocess.run(['whoami'],check=True,capture_output=True,text=True).stdout.strip()
        grants=[identity+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F']
        if operator_account:grants.append(operator_account+':(OI)(CI)F')
        result=subprocess.run(['icacls',str(runtime),'/inheritance:r','/grant:r',*grants],capture_output=True)
        if result.returncode:raise RuntimeError('Cannot restrict simulator runtime permissions')
    else:runtime.chmod(0o700)
    (runtime/'runs').mkdir(exist_ok=True)
    return runtime


def prepare(operator_account=None):
    command=['docker','compose','-f',str(APPLICATION/'infra/compose.yaml'),'run','--rm','--no-deps','-T','migrate','python','-']
    completed=subprocess.run(command,input=READ_TECHNICAL.encode(),capture_output=True)
    if completed.returncode:raise RuntimeError('Technical registry read refused; no private container output published')
    data=validate_metadata(json.loads(completed.stdout))
    runtime=private_runtime(operator_account)
    target=runtime/'transport.json';temporary=runtime/'transport.new'
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(data,stream,ensure_ascii=False,indent=2)
    temporary.replace(target)
    print('Simulator transport metadata prepared; no credentials copied and no calibration changed.')
    return target


def verify_run(run_id,operator_account=None):
    """Offline receipt proof; the web simulator never receives owner access."""
    run_id=str(UUID(run_id))
    command=['docker','compose','-f',str(APPLICATION/'infra/compose.yaml'),'run','--rm','--no-deps','-T','migrate','python','-',run_id]
    completed=subprocess.run(command,input=READ_RECEIPT.encode(),capture_output=True)
    if completed.returncode:raise RuntimeError('Receipt verification refused; no private container output published')
    proof=json.loads(completed.stdout)
    if proof.get('run_id')!=run_id or proof.get('device_id')!=DEVICE_ID:raise ValueError('Unexpected receipt identity')
    runtime=private_runtime(operator_account)
    target=runtime/'runs'/f'{run_id}.receipt.json'
    target.write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False))
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operator-account',help='Explicit Windows account running Docker Desktop if different from this process')
    parser.add_argument('--verify-run',help='Offline proof for one simulator session UUID; does not modify transport metadata')
    args=parser.parse_args()
    if args.verify_run:verify_run(args.verify_run,args.operator_account)
    else:prepare(args.operator_account)
