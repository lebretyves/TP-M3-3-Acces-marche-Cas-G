import importlib.util
from pathlib import Path
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('prepare_transport',ROOT/'prepare_transport.py')
transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)


def metadata():
    return {'device_id':'demo-device-a','cert_cn':'skm-001','calibration_version':'C-EXISTING','firmware_version':'2.4.2','algorithm_version':'gyro-v2-simulator','calibration_status':'required','technical_runtime':{'prepared_at':'2026-11-14T12:00:00+00:00','synthetic':True,'source':'fixed_device_registry','device_status':'active','certificate_revoked':False,'certificate_expires_at':9999999999,'last_window_end':None}}


def test_preserves_required_calibration_without_manufacturing_success():
    result=transport.validate_metadata(metadata())
    assert result['calibration_status']=='required'
    assert result['calibration_version']=='C-EXISTING'


@pytest.mark.parametrize('field,value',[('certificate_revoked',True),('certificate_expires_at',0),('certificate_expires_at',None),('certificate_expires_at',float('nan')),('certificate_expires_at',float('inf')),('device_status','retired'),('synthetic',False)])
def test_revoked_expired_and_retired_devices_refused(field,value):
    data=metadata();data['technical_runtime'][field]=value
    with pytest.raises(ValueError):transport.validate_metadata(data)


def test_cannot_select_another_device_or_copy_extra_sensitive_fields():
    data=metadata();data['device_id']='demo-device-b'
    with pytest.raises(ValueError):transport.validate_metadata(data)
    data=metadata();data['password']='forbidden'
    with pytest.raises(ValueError):transport.validate_metadata(data)


def test_overlay_has_private_broker_and_only_loopback_ui_port():
    config=yaml.safe_load((ROOT/'compose.yaml').read_text())['services']['simulator']
    assert config['ports']==['127.0.0.1:8774:8774']
    assert config['networks']==['private','edge'] and not config.get('secrets')
    assert config['read_only'] and 'ALL' in config['cap_drop']
    volumes=config['volumes']
    assert sum(not value.endswith(':ro') for value in volumes)==1
    assert all(not any(value in mount for value in ('offline-ca','owner_database_url','app_database_url','docker.sock')) for mount in volumes)
    assert config['environment']['SIMULATOR_MQTT_HOST']=='broker'
    assert config['environment']['SIMULATOR_OUTPUT_DIR']=='/run/simulator-runs'


def test_receipt_query_never_reads_measurement_content():
    assert 'Report.metrics' not in transport.READ_RECEIPT
    assert "IngestReceipt.device_id=='demo-device-a'" in transport.READ_RECEIPT
    assert 'IngestReceipt.session_id==run' in transport.READ_RECEIPT
    assert "Report.patient_id=='p-alice'" in transport.READ_RECEIPT


def test_receipt_run_id_must_be_uuid_before_operator_call():
    with pytest.raises(ValueError):transport.verify_run('not-a-session')
