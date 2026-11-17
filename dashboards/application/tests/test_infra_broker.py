"""Run explicitly inside the dedicated private Docker network; no host broker port."""
import json
import os
from pathlib import Path
import ssl
import socket
import threading
import time
from uuid import uuid4
import paho.mqtt.client as mqtt
import pytest

pytestmark=pytest.mark.skipif(os.getenv('SKELIVIA_LIVE_BROKER')!='1',reason='Explicit dedicated broker integration only')


def connect(identity, *, certificate=True, username=None):
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='probe-'+uuid4().hex,protocol=mqtt.MQTTv5)
    context=ssl.create_default_context(cafile='/pki/ca.pem')
    if username:client.username_pw_set(username)
    if certificate:context.load_cert_chain('/identities/'+identity+'/cert.pem','/identities/'+identity+'/key.pem')
    client.tls_set_context(context)
    client.connected=threading.Event();client.published=threading.Event();client.messages=[];client.reasons=[]
    client.on_connect=lambda c,u,f,r,p: c.connected.set() if not r.is_failure else None
    client.on_publish=lambda c,u,m,r,p:(c.reasons.append(r.value),c.published.set())
    client.on_message=lambda c,u,m:c.messages.append((m.topic,m.payload))
    client.connect('broker',8883,keepalive=10);client.loop_start()
    if not client.connected.wait(4):
        client.loop_stop();client.disconnect()
        raise ConnectionError('TLS/client authentication rejected')
    return client


def publish(client,topic):
    client.published.clear();client.reasons.clear()
    client.publish(topic,b'{"probe":"synthetic transport only"}',qos=1,retain=False)
    assert client.published.wait(4),'No broker acknowledgement'
    return client.reasons[-1]


def test_broker_mtls_and_acl():
    clients=[]
    try:
        with pytest.raises(OSError):socket.create_connection(('broker',1883),timeout=2)
        with pytest.raises((ssl.SSLError,ConnectionError,OSError)):connect('skm-001',certificate=False)
        first=connect('skm-001',username='skm-002');clients.append(first)
        second=connect('skm-002');clients.append(second)
        worker=connect('worker');clients.append(worker)
        worker.subscribe('skelivia/v1/devices/+/telemetry',qos=1)
        first.subscribe('skelivia/v1/devices/+/commands',qos=1)
        second.subscribe('skelivia/v1/devices/+/telemetry',qos=1)
        time.sleep(.3)
        assert publish(first,'skelivia/v1/devices/skm-001/telemetry')<128
        assert publish(first,'skelivia/v1/devices/skm-002/telemetry')>=128
        assert publish(worker,'skelivia/v1/devices/skm-001/telemetry')>=128
        assert publish(worker,'skelivia/v1/devices/skm-002/commands')<128
        time.sleep(.3)
        assert any(t.endswith('skm-001/telemetry') for t,p in worker.messages)
        assert not first.messages,'Device received another device command'
        assert not second.messages,'Device received another device telemetry'
    finally:
        for client in clients:client.disconnect();client.loop_stop()


def test_revoked_certificate_rejected():
    with pytest.raises((ssl.SSLError,ConnectionError,OSError)):
        connect('probe-revoked')


if __name__=='__main__':
    test_broker_mtls_and_acl()
    print(json.dumps({'mtls_required':True,'own_publish':True,'foreign_publish_denied':True,'worker_publish_telemetry_denied':True,'foreign_subscription_receives_no_data':True}))
