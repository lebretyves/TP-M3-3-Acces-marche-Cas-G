import importlib.util
from pathlib import Path
import pytest
import yaml
from cryptography.exceptions import InvalidTag

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('backup_restore',ROOT/'scripts/backup_restore.py')
backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)


def test_authenticated_backup_refuses_tamper_wrong_key_and_plaintext():
    key=b'k'*32; original=b'private synthetic dump'
    sealed=backup.seal(original,key)
    assert original not in sealed and backup.unseal(sealed,key)==original
    with pytest.raises(InvalidTag):backup.unseal(sealed,b'z'*32)
    with pytest.raises(InvalidTag):backup.unseal(sealed[:-1]+bytes([sealed[-1]^1]),key)
    with pytest.raises(ValueError):backup.unseal(original,key)


def test_compose_has_only_loopback_https_and_no_docker_socket():
    config=yaml.safe_load((ROOT/'infra/compose.yaml').read_text())
    assert config['name']=='skelivia'
    assert config['networks']['private']['internal'] is True
    for name,service in config['services'].items():
        if name=='proxy':assert service['ports']==['127.0.0.1:8443:443']
        else:assert not service.get('ports')
        assert all('docker.sock' not in str(v) for v in service.get('volumes',[]))
        assert all('offline-ca' not in str(v) for v in service.get('volumes',[]))
    for name in ('app','worker'):
        service=config['services'][name]
        assert service['read_only'] and 'ALL' in service['cap_drop']
        assert 'SKELIVIA_DATABASE_URL_FILE' in service['environment']


def test_mqtt_requires_client_certificate_and_crl():
    conf=(ROOT/'infra/mosquitto.conf').read_text()
    for line in ('require_certificate true','use_identity_as_username true','allow_anonymous false','crlfile /mosquitto/pki/crl.pem'):
        assert line in conf
    assert 'listener 1883' not in conf


def test_optional_simulator_proxy_does_not_resolve_at_startup_or_relax_global_frames():
    conf=(ROOT/'infra/nginx.conf').read_text()
    simulator=conf.split('location /simulateur/ {',1)[1].split('\n    }',1)[0]
    assert 'resolver 127.0.0.11 valid=10s ipv6=off;' in simulator
    assert 'set $simulator_backend simulator:8774;' in simulator
    assert 'proxy_set_header X-Forwarded-Prefix /simulateur;' in simulator
    for header in ('Host localhost:8443','X-Forwarded-Host localhost:8443','X-Forwarded-Port 8443','X-Forwarded-Proto https','X-Forwarded-For $remote_addr'):
        assert 'proxy_set_header '+header+';' in simulator
    assert 'proxy_pass http://$simulator_backend;' in simulator
    assert 'rewrite ^/simulateur/(.*)$ /$1 break;' in simulator
    assert 'proxy_pass http://simulator:' not in conf
    launcher=conf.split('location = /static/simulation.html {',1)[1].split('\n    }',1)[0]
    assert 'proxy_hide_header X-Frame-Options;' in launcher
    assert 'add_header X-Frame-Options SAMEORIGIN always;' in launcher
    assert conf.count('add_header X-Frame-Options SAMEORIGIN always;')==1
    assert 'add_header X-Frame-Options DENY always;' in conf


def test_restore_name_cannot_address_production():
    assert not backup.RESTORE_NAME.fullmatch('skelivia')
    assert not backup.RESTORE_NAME.fullmatch('p2')
    assert not backup.RESTORE_NAME.fullmatch('skelivia_restore_;DROP DATABASE p2')


def test_realm_requires_password_otp_and_pkce():
    spec=importlib.util.spec_from_file_location('prepare',ROOT/'scripts/prepare_infra.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    realm=module.make_realm('not-real',{a:'not-real' for a in module.ACCOUNTS})
    client=realm['clients'][0]
    assert client['publicClient'] is False and not client['directAccessGrantsEnabled']
    assert client['attributes']['pkce.code.challenge.method']=='S256'
    assert client['attributes']['default.acr.values']=='2'
    executions=realm['authenticationFlows'][1]['authenticationExecutions']
    assert all(e['requirement']=='REQUIRED' for e in executions)
    assert {'auth-username-password-form','auth-otp-form'} <= {e['authenticator'] for e in executions}
    assert all(u['requiredActions']==['CONFIGURE_TOTP'] for u in realm['users'])


def test_restoration_reapplies_deletion_and_revokes_all_access(tmp_path,monkeypatch):
    import base64
    from sqlalchemy import create_engine,select
    from sqlalchemy.orm import sessionmaker
    from app.models import Base,Report,Share,WebSession,Account
    from app.domain_models import DomainRecord,DomainGrant,DomainDiagnostic
    from app.transport_models import DeviceIdentity
    key=tmp_path/'key';key.write_bytes(base64.b64encode(b'q'*32));monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(key))
    engine=create_engine('sqlite:///'+str(tmp_path/'restore.db'));Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory.begin() as db:
        db.add(Account(id='u',username='deleted-user',name='Private name',role='user',org_id='test',patient_id='deleted-patient',password_hash='unused',otp_secret='unused',active=True))
        db.add(Account(id='unrelated',username='other-user',name='Retained name',role='user',org_id='test',patient_id='other-patient',password_hash='unused',otp_secret='unused',active=True))
        db.add(DomainRecord(id='private-settings',kind='settings',owner_id='u',data={'private':'must not reappear'},created_at=0,updated_at=0))
        db.add(Report(id='old',patient_id='deleted-patient',title='synthetic',recorded_at='2026-11-14',quality='valid',metrics={'contact_seconds':3},synthetic=True))
        db.add(Share(id='s',report_id='old',clinician_id='c',active=True,expires=9999999999))
        db.add(DomainGrant(id='g',owner_id='u',patient_id='deleted-patient',clinician_id='c',start='2026-01-01',end='2026-12-31',categories=[],expires=9999999999,active=True))
        db.add(WebSession(token_hash='x',user_id='u',csrf='x',expires=9999999999,last_seen=0))
        db.add(DomainRecord(id='device',kind='device',patient_id='deleted-patient',data={},created_at=0,updated_at=0))
        db.add(DeviceIdentity(cert_cn='revoked',device_id='device',cert_serial='1'))
        db.add(DomainDiagnostic(ticket_id='t',device_id='device',support_id='s',owner_id='u',expires=9999999999,active=True))
    backup.reconcile(factory,{'version':1,'deleted_patients':['deleted-patient'],'deleted_subjects':[{'patient_id':'deleted-patient','account_id':'u','request_id':'deletion-proof','proof_reference':'proof-v1'}],'disabled_accounts':[],'revoked_devices':['revoked']})
    with factory() as db:
        assert db.get(Report,'old') is None and db.get(Share,'s') is None
        assert db.get(DomainGrant,'g') is None and db.get(DomainRecord,'device').status=='retired'
        assert db.scalar(select(WebSession)) is None
        assert not db.get(DomainDiagnostic,'t').active
        assert db.get(DeviceIdentity,'revoked').revoked_at is not None
        assert db.get(Account,'u') is None and db.get(DomainRecord,'private-settings') is None
        assert db.get(Account,'unrelated') is not None
        assert db.get(DomainRecord,'deletion-proof').status=='completed'
