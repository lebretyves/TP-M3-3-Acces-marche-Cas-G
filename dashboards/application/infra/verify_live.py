"""Explicit synthetic-bank integration verification. Does not revoke active devices."""
import contextlib
from datetime import datetime,timezone
import importlib.util
import io
import json
from pathlib import Path
import ssl
import subprocess
import urllib.request
from cryptography import x509

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/'.runtime/infra'
COMPOSE=['docker','compose','-f',str(ROOT/'infra/compose.yaml')]


def checked(command,code=None):
    result=subprocess.run(command,input=code.encode() if code else None,capture_output=True)
    if result.returncode:raise RuntimeError('Integration operation failed; restricted raw output not published')
    return result.stdout.decode()


def mount(source,target):return ['--mount',f'type=bind,source={source},target={target},readonly']


def container():
    return ['docker','run','--rm','--network','skelivia_private','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true']


def json_lines(output):return [json.loads(line) for line in output.splitlines() if line.startswith('{')]


def main():
    result={'at':datetime.now(timezone.utc).isoformat(),'scope':'dedicated_local_synthetic_skelivia','production_security_certification':False}
    # Public leaf certificate inspection explains host interception without trusting it.
    context=ssl.create_default_context(cafile=str(RUNTIME/'pki/public/ca.pem'))
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context))
        with opener.open('https://localhost:8443/api/health',timeout=5) as response:result['host_tls']={'status':'verified','http_status':response.status}
    except Exception as error:
        cert=x509.load_pem_x509_certificate(ssl.get_server_certificate(('localhost',8443)).encode())
        result['host_tls']={'status':'verification_refused','exception_type':type(error).__name__,'presented_issuer':cert.issuer.rfc4514_string(),'note':'No trust bypass applied; public certificate inspection only.'}
    tls_code="""import ssl,urllib.request,urllib.error,json
ctx=ssl.create_default_context(cafile='/run/pki/ca.pem');opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=ctx));r={}
for p in ['/api/health','/auth/realms/skelivia/.well-known/openid-configuration','/auth/realms/master/.well-known/openid-configuration','/auth/admin/']:
 try:
  with opener.open('https://proxy'+p,timeout=5) as x:r[p]=x.status
 except urllib.error.HTTPError as e:r[p]=e.code
assert list(r.values())==[200,200,403,403];print(json.dumps({'strict_ca_validation':True,'routes':r}))
"""
    result['private_https']=json_lines(checked([*COMPOSE,'exec','-T','worker','python','-'],tls_code))[0]
    broker=container()+mount(RUNTIME/'pki/public','/pki')
    for cn in ('skm-001','skm-002','worker','probe-revoked'):broker+=mount(RUNTIME/'pki'/cn,'/identities/'+cn)
    broker+=mount(ROOT/'tests/test_infra_broker.py','/test.py')
    broker+=['skelivia-local:development','python','-c',"import sys,json;sys.path.insert(0,'/');from test import test_broker_mtls_and_acl,test_revoked_certificate_rejected;test_broker_mtls_and_acl();test_revoked_certificate_rejected();print(json.dumps({'mtls_required':True,'plaintext_listener_absent':True,'certificate_cn_overrides_mqtt_username':True,'cross_device_topics_denied':True,'worker_cannot_publish_measurements':True,'revoked_test_certificate_denied':True}))"]
    result['broker']=json_lines(checked(broker))[0]
    worker=container()+['-e','SKELIVIA_DATA_KEY_FILE=/run/data_key','-e','PYTHONPATH=/srv/skelivia']+mount(RUNTIME/'pki/public','/pki')+mount(RUNTIME/'pki/skm-001','/device')
    for name in ('owner_database_url','worker_database_url','data_key'):worker+=mount(RUNTIME/'secrets'/name,'/run/'+name)
    worker+=mount(ROOT/'tests/test_infra_worker_live.py','/test.py')+['skelivia-local:development','python','/test.py']
    result['postgres_worker']=json_lines(checked(worker))
    config="from app.database import runtime_url;from sqlalchemy import create_engine,text;import os,json;e=create_engine(runtime_url(),hide_parameters=True);c=e.connect();print(json.dumps({'role':c.execute(text('SELECT current_user')).scalar(),'enabled':os.getenv('SKELIVIA_PUSH_ENABLED')}));c.close();e.dispose()"
    push=json_lines(checked([*COMPOSE,'exec','-T','push','python','-c',config]))[0]
    assert push=={'role':'skelivia_push','enabled':'false'},'External sends must remain disabled for this verification'
    checked([*COMPOSE,'exec','-T','push','python','-m','app.push','--once'])
    result['push']={**push,'cycle':'PASS','external_send_attempted':False}
    spec=importlib.util.spec_from_file_location('backup_adapter',ROOT/'scripts/backup_restore.py');backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        archive=backup.backup();backup.restore(archive)
    records=json_lines(output.getvalue())
    records[0]['file']=Path(records[0]['file']).name
    result['backup_restore']=records
    proof_code="""from app.database import database
from app.security_monitor import snapshot
from app.domain_models import DomainRecord
import json
e,s=database()
with s() as d:
 p=d.get(DomainRecord,'backup-state').data;print(json.dumps({'heartbeat':snapshot(d),'backup_verified':p['verified'],'backup_duration_seconds':p['last_backup']['duration_seconds'],'restore_duration_seconds':p['last_restore']['duration_seconds'],'revocations_reapplied':p['last_restore']['revocations_reapplied']}))
e.dispose()
"""
    result['operational_proof']=json_lines(checked([*COMPOSE,'run','--rm','--no-deps','-T','migrate','python','-'],proof_code))[0]
    checked([str(ROOT/'.venv/Scripts/python.exe'),str(ROOT/'scripts/prepare_infra.py'),'--record-inventory'])
    result['inventory']=json.loads((ROOT/'infra/inventory-observed.json').read_text())
    result['limitations']=['Synthetic telemetry and non-flashable signed firmware fixture only.','Revocation workflow unit-tested on disposable data; active device certificates not revoked.','No physical sensor validation, PSC/HDS certification or off-site recovery claim.','Phone/watch outbound push disabled.']
    destination=ROOT.parent/'verification/infra-live-results.json';destination.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('SKELIVIA integration evidence saved: '+str(destination))


if __name__=='__main__':main()
