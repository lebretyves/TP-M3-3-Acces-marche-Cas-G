"""Generate an isolated local bank. Idempotent; never prints credential material."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import secrets
import re
import subprocess
from uuid import NAMESPACE_URL, uuid5
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import ec
from hashlib import sha256
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / '.runtime' / 'infra'
ACCOUNTS = ('u-alice', 'u-benoit', 'c-lina', 'c-marc', 'e-atelier', 't-support', 's-securite', 's-approbateur')
DEVICES = (('skm-001', 'demo-device-a'), ('skm-002', 'demo-device-b'))


def private_directory(path, operator_account=None):
    path.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        identity = subprocess.run(['whoami'], check=True, capture_output=True, text=True).stdout.strip()
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', identity + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F', '*S-1-5-32-544:(OI)(CI)F'], capture_output=True)
        if result.returncode:
            raise RuntimeError('Cannot restrict runtime directory ACL; preparation stopped.')
        if operator_account:
            result = subprocess.run(['icacls', str(path), '/grant:r', operator_account + ':(OI)(CI)F'], capture_output=True)
            if result.returncode:
                raise RuntimeError('Cannot grant explicit operator account access.')
    else:
        path.chmod(0o700)


def write_private(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, str):
        data = data.encode()
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(data)


def secret(root, name, *, raw=None):
    path = root / 'secrets' / name
    if not path.exists():
        write_private(path, raw or secrets.token_urlsafe(36))
    return path.read_text().strip()


def issue_cert(root, ca_key, ca_cert, name, *, server=False, dns=()):
    target = root / 'pki' / name
    if (target / 'cert.pem').exists():
        return x509.load_pem_x509_certificate((target / 'cert.pem').read_bytes())
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=True, data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True))
    if dns:
        names = [x509.DNSName(host) for host in dns]
        if 'localhost' in dns:
            names.append(x509.IPAddress(ipaddress.ip_address('127.0.0.1')))
        builder = builder.add_extension(x509.SubjectAlternativeName(names), critical=False)
    cert = builder.sign(ca_key, hashes.SHA256())
    write_private(target / 'key.pem', key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    write_private(target / 'cert.pem', cert.public_bytes(serialization.Encoding.PEM))
    return cert


def generate_pki(root):
    passphrase = secret(root, 'ca_key_password').encode()
    capath = root / 'pki' / 'offline-ca' / 'key.pem'
    certpath = root / 'pki' / 'public' / 'ca.pem'
    now = datetime.now(timezone.utc)
    if capath.exists():
        key = serialization.load_pem_private_key(capath.read_bytes(), passphrase)
        cert = x509.load_pem_x509_certificate(certpath.read_bytes())
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'SKELIVIA local synthetic CA')])
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False, data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
        write_private(capath, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.BestAvailableEncryption(passphrase)))
        write_private(certpath, cert.public_bytes(serialization.Encoding.PEM))
    crlpath = root / 'pki' / 'public' / 'crl.pem'
    if not crlpath.exists():
        crl = x509.CertificateRevocationListBuilder().issuer_name(cert.subject).last_update(now).next_update(now+timedelta(days=30)).sign(key, hashes.SHA256())
        write_private(crlpath, crl.public_bytes(serialization.Encoding.PEM))
    issue_cert(root, key, cert, 'broker', server=True, dns=('broker',))
    issue_cert(root, key, cert, 'proxy', server=True, dns=('proxy', 'localhost'))
    issue_cert(root, key, cert, 'worker')
    registry = []
    for cn, device_id in DEVICES:
        device = issue_cert(root, key, cert, cn)
        registry.append({'cert_cn':cn, 'device_id':device_id, 'cert_serial':str(device.serial_number), 'expires_at':device.not_valid_after_utc.timestamp()})
    path = root / 'registry' / 'devices.json'
    if not path.exists():
        write_private(path, json.dumps(registry, indent=2))


def revoke_certificate(root, cn):
    """Prepare a signed CRL. Operator must then reload/restart the dedicated broker.

    Existing connections require disconnection: a CRL only gates TLS handshakes.
    Runtime registry records the revocation for the migration/operator adapter.
    """
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', cn) or cn in ('proxy','broker','worker'):
        raise ValueError('Only a named device certificate may be revoked here')
    cert=x509.load_pem_x509_certificate((root/'pki'/cn/'cert.pem').read_bytes())
    ca=x509.load_pem_x509_certificate((root/'pki/public/ca.pem').read_bytes())
    key=serialization.load_pem_private_key((root/'pki/offline-ca/key.pem').read_bytes(),(root/'secrets/ca_key_password').read_bytes().strip())
    now=datetime.now(timezone.utc)
    current=x509.load_pem_x509_crl((root/'pki/public/crl.pem').read_bytes())
    builder=x509.CertificateRevocationListBuilder().issuer_name(ca.subject).last_update(now).next_update(now+timedelta(days=30))
    for revoked in current:builder=builder.add_revoked_certificate(revoked)
    if not current.get_revoked_certificate_by_serial_number(cert.serial_number):
        builder=builder.add_revoked_certificate(x509.RevokedCertificateBuilder().serial_number(cert.serial_number).revocation_date(now).build())
    path=root/'pki/public/crl.pem'; temporary=path.with_suffix('.new')
    write_private(temporary,builder.sign(key,hashes.SHA256()).public_bytes(serialization.Encoding.PEM))
    temporary.replace(path)
    registry=root/'registry/devices.json'
    rows=json.loads(registry.read_text())
    for row in rows:
        if row['cert_cn']==cn: row['revoked_at']=row.get('revoked_at') or now.timestamp()
    registry.write_text(json.dumps(rows,indent=2))
    print('Signed CRL prepared. Apply database revocation and restart only the SKELIVIA broker to terminate existing sessions.')


def synthetic_firmware(root):
    """Signed test fixture, deliberately not an ESP32 executable or real update."""
    target=root/'firmware'
    if (target/'manifest.json').exists():return
    key=Ed25519PrivateKey.generate()
    write_private(root/'pki/offline-firmware/key.pem',key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    write_private(target/'signing-public.pem',key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    payload=b'SKELIVIA SYNTHETIC FIRMWARE TEST FIXTURE v2.4.2 - NOT FLASHABLE\n'
    write_private(target/'synthetic-2.4.2.bin',payload)
    item={'patch_id':'patch-demo','version':'2.4.2','sha256':sha256(payload).hexdigest(),'synthetic':True}
    signed=json.dumps(item,sort_keys=True,separators=(',',':')).encode()
    item.update(file='synthetic-2.4.2.bin',signature=base64.b64encode(key.sign(signed)).decode())
    write_private(target/'manifest.json',json.dumps({'version':1,'artifacts':[item]},indent=2))


def record_inventory():
    import yaml
    compose=['docker','compose','-f',str(ROOT/'infra/compose.yaml')]
    config=yaml.safe_load((ROOT/'infra/compose.yaml').read_text())
    ids=subprocess.run(['docker','ps','-q','--filter','label=com.docker.compose.project=skelivia'],check=True,capture_output=True,text=True).stdout.split()
    if not ids:raise RuntimeError('No running SKELIVIA services')
    template='{{ index .Config.Labels "com.docker.compose.service" }}|{{.Image}}|{{.Config.Image}}|{{.State.Status}}'
    lines=subprocess.run(['docker','inspect','--format',template,*ids],check=True,capture_output=True,text=True).stdout.splitlines()
    components=[]
    for line in lines:
        service,image_id,observed,state=line.split('|')
        if service not in config['services'] or service=='migrate':continue
        declared=config['services'][service]['image']
        expected=subprocess.run(['docker','image','inspect','--format','{{.Id}}',declared],check=True,capture_output=True,text=True).stdout.strip()
        components.append({'service':service,'version':declared.split('@')[0],'configured_image':declared,'observed_image_id':image_id,'matches_configured_image':image_id==expected,'state':state})
    code="import hashlib,json,platform,importlib.metadata as m;from pathlib import Path;files=sorted(Path('app').rglob('*.py'));h=hashlib.sha256();[(h.update(str(p).encode()),h.update(p.read_bytes())) for p in files];print(json.dumps({'source':h.hexdigest(),'python':platform.python_version(),'fastapi':m.version('fastapi'),'paho':m.version('paho-mqtt'),'pywebpush':m.version('pywebpush')}))"
    observed=json.loads(subprocess.run([*compose,'exec','-T','app','python','-c',code],check=True,capture_output=True,text=True).stdout)
    for component in components:
        if component['service']=='app':component['version']='FastAPI '+observed['fastapi']+' / Python '+observed['python']
        elif component['service']=='worker':component['version']='Paho MQTT '+observed['paho']+' / Python '+observed['python']
        elif component['service']=='push':component['version']='pywebpush '+observed['pywebpush']+' / Python '+observed['python']
    payload={'at':datetime.now(timezone.utc).isoformat(),'components':components,'application_source_sha256':observed['source']}
    result=subprocess.run([*compose,'run','--rm','--no-deps','-T','migrate','python','scripts/backup_restore.py','inventory'],input=json.dumps(payload).encode(),capture_output=True)
    if result.returncode:raise RuntimeError('Inventory recording failed; no raw container output published')
    (ROOT/'infra/inventory-observed.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print('Observed local component inventory recorded without credentials or invented end-of-support dates.')


def certificate_job(job_id, *, execute=False, root=DEFAULT):
    """Offline operator orchestration, defaults to a read-only execution plan."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',job_id):raise ValueError('Invalid job identifier')
    compose=['docker','compose','-f',str(ROOT/'infra/compose.yaml')]
    def database_phase(payload):
        result=subprocess.run([*compose,'run','--rm','--no-deps','-T','migrate','python','scripts/backup_restore.py','certificate'],input=json.dumps(payload).encode(),capture_output=True)
        if result.returncode:raise RuntimeError('Certificate database operation refused; no raw output published')
        return json.loads(result.stdout)
    plan=database_phase({'phase':'plan','job_id':job_id})
    if not execute:
        print(json.dumps(plan));return plan
    if plan['operation']!='revoke':raise ValueError('Renewal awaits verified device installation; no automatic success')
    if plan['status']=='completed':print('Certificate revocation already completed.');return plan
    cn=plan['cert_cn']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',cn):raise ValueError('Invalid certificate CN')
    actual=x509.load_pem_x509_certificate((root/'pki'/cn/'cert.pem').read_bytes())
    if str(actual.serial_number)!=plan['cert_serial']:raise ValueError('Issued certificate does not match pending job')
    revoke_certificate(root,cn)
    database_phase({'phase':'stage','job_id':job_id,'cert_serial':plan['cert_serial']})
    subprocess.run([*compose,'restart','broker'],check=True,capture_output=True)
    # Require a certificate-revoked TLS alert, not merely a network timeout/refusal.
    code="""import ssl,socket,time
ctx=ssl.create_default_context(cafile='/pki/ca.pem');ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.maximum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain('/device/cert.pem','/device/key.pem')
for attempt in range(10):
 try:
  with socket.create_connection(('broker',8883),timeout=2) as sock:
   with ctx.wrap_socket(sock,server_hostname='broker'):raise RuntimeError('Revoked certificate was accepted')
 except ssl.SSLError as error:
  if 'CERTIFICATE_REVOKED' in error.reason:break
  raise
 except (ConnectionError,TimeoutError):time.sleep(.5)
else:raise RuntimeError('Broker unavailable: revocation not verified')
print('revoked_tls_verified')
"""
    command=['docker','run','--rm','--network','skelivia_private','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true',
      '--mount','type=bind,source='+str((root/'pki/public').resolve())+',target=/pki,readonly',
      '--mount','type=bind,source='+str((root/'pki'/cn).resolve())+',target=/device,readonly','skelivia-local:development','python','-c',code]
    verified=subprocess.run(command,capture_output=True)
    if verified.returncode or verified.stdout.strip()!=b'revoked_tls_verified':raise RuntimeError('TLS revocation test failed; job remains pending disconnect')
    completed=database_phase({'phase':'complete','job_id':job_id,'cert_serial':plan['cert_serial'],'tls_rejection_verified':True,'crl_sha256':sha256((root/'pki/public/crl.pem').read_bytes()).hexdigest()})
    print(json.dumps(completed));return completed


def make_realm(client_secret, passwords):
    # LoA is granted by the conditional subflow only after password AND OTP.
    return {
        'realm':'skelivia', 'enabled':True, 'sslRequired':'external', 'registrationAllowed':False,
        'resetPasswordAllowed':False, 'rememberMe':False, 'bruteForceProtected':True,
        'failureFactor':5, 'waitIncrementSeconds':60, 'maxFailureWaitSeconds':900,
        'accessTokenLifespan':300, 'ssoSessionIdleTimeout':900, 'ssoSessionMaxLifespan':28800,
        'otpPolicyType':'totp', 'otpPolicyAlgorithm':'HmacSHA256', 'otpPolicyDigits':6,
        'otpPolicyPeriod':30, 'otpPolicyLookAheadWindow':1,
        'browserFlow':'skelivia-browser',
        'authenticationFlows':[
            {'alias':'skelivia-browser','providerId':'basic-flow','topLevel':True,'builtIn':False,
             'authenticationExecutions':[{'authenticatorFlow':True,'flowAlias':'skelivia-loa2','requirement':'CONDITIONAL','priority':10}]},
            {'alias':'skelivia-loa2','providerId':'basic-flow','topLevel':False,'builtIn':False,
             'authenticationExecutions':[
                 {'authenticator':'conditional-level-of-authentication','authenticatorConfig':'skelivia-level2','requirement':'REQUIRED','priority':10,'authenticatorFlow':False},
                 {'authenticator':'auth-username-password-form','requirement':'REQUIRED','priority':20,'authenticatorFlow':False},
                 {'authenticator':'auth-otp-form','requirement':'REQUIRED','priority':30,'authenticatorFlow':False}]}],
        'authenticatorConfig':[{'alias':'skelivia-level2','config':{'loa-condition-level':'2','loa-max-age':'0','loa-store-in-user-session':'false'}}],
        'requiredActions':[{'alias':'CONFIGURE_TOTP','name':'Configure OTP','providerId':'CONFIGURE_TOTP','enabled':True,'defaultAction':True,'priority':10}],
        'clients':[{
            'clientId':'skelivia-web','name':'SKELIVIA local bank','enabled':True,'protocol':'openid-connect',
            'publicClient':False,'secret':client_secret,'standardFlowEnabled':True,
            'directAccessGrantsEnabled':False,'serviceAccountsEnabled':False,'implicitFlowEnabled':False,
            'redirectUris':['https://localhost:8443/oidc/callback'], 'webOrigins':['https://localhost:8443'],
            'attributes':{'pkce.code.challenge.method':'S256','default.acr.values':'2','minimum.acr.value':'2',
                'backchannel.logout.url':'http://app:8000/oidc/backchannel-logout','backchannel.logout.session.required':'true'},
            'defaultClientScopes':['basic','web-origins','acr','profile','email'], 'optionalClientScopes':[],
            'protocolMappers':[{'name':'acr','protocol':'openid-connect','protocolMapper':'oidc-acr-mapper','consentRequired':False,'config':{'id.token.claim':'true','access.token.claim':'true'}}]
        }],
        'users':[{'id':str(uuid5(NAMESPACE_URL,'skelivia-local:'+account)), 'username':account,
                  'enabled':True,'emailVerified':False,'firstName':account,'lastName':'Banc fictif',
                  'requiredActions':['CONFIGURE_TOTP'],
                  'credentials':[{'type':'password','value':passwords[account],'temporary':False}]} for account in ACCOUNTS]
    }


def prepare(root=DEFAULT, operator_account=None):
    root = root.resolve()
    if not root.is_relative_to(ROOT.resolve()):
        raise ValueError('runtime must remain inside dashboards/application')
    private_directory(root, operator_account)
    postgres = secret(root, 'postgres_password')
    client = secret(root, 'oidc_client_secret')
    secret(root, 'keycloak_admin_password')
    secret(root, 'data_key', raw=base64.b64encode(secrets.token_bytes(32)))
    secret(root, 'backup_key', raw=base64.b64encode(secrets.token_bytes(32)))
    dbpasswords = {role:secret(root,role+'_password') for role in ('owner','app','worker','push','keycloak_db')}
    for role in ('owner','app','worker','push'):
        path = root / 'secrets' / (role+'_database_url')
        if not path.exists():
            write_private(path, f'postgresql+psycopg://skelivia_{role}:{dbpasswords[role]}@db:5432/skelivia')
    sql = '\n'.join(f"CREATE ROLE skelivia_{role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{dbpasswords[role]}';" for role in ('owner','app','worker','push'))
    sql += f"\nCREATE ROLE skelivia_keycloak LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD '{dbpasswords['keycloak_db']}';\n"
    sql += 'CREATE DATABASE skelivia OWNER skelivia_owner;\nCREATE DATABASE skelivia_identity OWNER skelivia_keycloak;\n'
    sql += 'REVOKE ALL ON DATABASE skelivia FROM PUBLIC;\nGRANT CONNECT ON DATABASE skelivia TO skelivia_app, skelivia_worker, skelivia_push;\n'
    sql += '\\connect skelivia\nREVOKE CREATE ON SCHEMA public FROM PUBLIC;\nGRANT USAGE ON SCHEMA public TO skelivia_app, skelivia_worker, skelivia_push;\n'
    if not (root/'postgres/init.sql').exists():
        write_private(root/'postgres/init.sql', sql)
    passwords = {account:secret(root,'login_'+account) for account in ACCOUNTS}
    if not (root/'keycloak/skelivia-realm.json').exists():
        write_private(root/'keycloak/skelivia-realm.json', json.dumps(make_realm(client,passwords),ensure_ascii=False,indent=2))
    mapping = {str(uuid5(NAMESPACE_URL,'skelivia-local:'+account)):account for account in ACCOUNTS}
    if not (root/'secrets/identity-map.json').exists():
        write_private(root/'secrets/identity-map.json',json.dumps(mapping,indent=2))
    generate_pki(root)
    synthetic_firmware(root)
    if not (root/'secrets/vapid_private.pem').exists():
        vapid=ec.generate_private_key(ec.SECP256R1())
        write_private(root/'secrets/vapid_private.pem',vapid.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        write_private(root/'secrets/vapid_public_key',base64.urlsafe_b64encode(vapid.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)).rstrip(b'='))
    # Explicit users, rather than global patterns, also prevent worker publishing telemetry.
    acl = 'user worker\ntopic read skelivia/v1/devices/+/telemetry\ntopic read skelivia/v1/devices/+/ack\ntopic write skelivia/v1/devices/+/commands\n'
    for cn, _ in DEVICES:
        acl += f'\nuser {cn}\ntopic write skelivia/v1/devices/{cn}/telemetry\ntopic write skelivia/v1/devices/{cn}/ack\ntopic read skelivia/v1/devices/{cn}/commands\n'
    if not (root/'mqtt/acl').exists():
        write_private(root/'mqtt/acl', acl)
    print('SKELIVIA local configuration prepared; private runtime files only. No containers started.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=DEFAULT)
    parser.add_argument('--operator-account', help='Explicit Windows user running Docker Desktop, if different from this process')
    parser.add_argument('--revoke', help='Prepare CRL for one issued device CN; never rotates or deletes keys')
    parser.add_argument('--record-inventory',action='store_true',help='Record versions/images observed in running SKELIVIA containers')
    parser.add_argument('--certificate-job',help='Plan a validated certificate job using dedicated operator credentials')
    parser.add_argument('--execute',action='store_true',help='Explicitly execute a pending certificate revocation; defaults to dry-run')
    args=parser.parse_args()
    if args.certificate_job:certificate_job(args.certificate_job,execute=args.execute,root=args.runtime)
    elif args.execute:parser.error('--execute requires --certificate-job')
    elif args.record_inventory:record_inventory()
    elif args.revoke: revoke_certificate(args.runtime,args.revoke)
    else: prepare(args.runtime,args.operator_account)
