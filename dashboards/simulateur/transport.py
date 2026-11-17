"""Device-scoped mTLS publisher. A PUBACK is not a database receipt."""
import json
import os
from pathlib import Path
import re
import ssl
import threading
import uuid
import paho.mqtt.client as mqtt


class TransportUnavailable(RuntimeError):
    pass


class Publisher:
    def __init__(self):
        self.client=None
        self.connected=False
        self.meta={}
        self.ready=threading.Event()
        self.condition=threading.Condition()
        self.acks={}

    def configuration(self):
        filename=os.getenv('SIMULATOR_CONFIG_FILE','')
        try:
            meta=json.loads(Path(filename).read_text(encoding='utf-8'))
            if meta.get('device_id')!='demo-device-a' or meta.get('cert_cn')!='skm-001':raise ValueError()
            for field in ('calibration_version','firmware_version','algorithm_version'):
                if not re.fullmatch(r'[A-Za-z0-9._-]{1,40}',meta[field]):raise ValueError()
            for key in ('CA','CERT','KEY'):
                if not Path(os.environ['SIMULATOR_MQTT_'+key+'_FILE']).is_file():raise ValueError()
            self.meta=meta
            return True
        except (ValueError,KeyError,OSError):return False

    def status(self):
        configured=self.configuration()
        return {'configured':configured,'connected':self.connected,'device_id':'demo-device-a',
                'calibration_status':self.meta.get('calibration_status','unknown'),'calibration_version':self.meta.get('calibration_version'),
                'detail':'Transmission vers la souris fictive Alice. Accusé MQTT distinct de l’enregistrement en base.' if configured else 'Transport non préparé : utilisez le lanceur du simulateur. L’aperçu reste disponible.'}

    def connect(self):
        if not self.configuration():raise TransportUnavailable('Configuration du transport indisponible.')
        self.ready.clear();self.acks.clear()
        client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='simulator-'+uuid.uuid4().hex,protocol=mqtt.MQTTv5)
        context=ssl.create_default_context(cafile=os.environ['SIMULATOR_MQTT_CA_FILE'])
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(os.environ['SIMULATOR_MQTT_CERT_FILE'],os.environ['SIMULATOR_MQTT_KEY_FILE'])
        client.tls_set_context(context)
        def connected(c,u,flags,reason,properties):
            self.connected=not reason.is_failure;self.ready.set()
        def disconnected(c,u,flags,reason,properties):self.connected=False
        def published(c,u,mid,reason,properties):
            with self.condition:
                self.acks[mid]=not reason.is_failure
                self.condition.notify_all()
        client.on_connect=connected;client.on_disconnect=disconnected;client.on_publish=published
        self.client=client
        client.connect_async(os.getenv('SIMULATOR_MQTT_HOST','broker'),int(os.getenv('SIMULATOR_MQTT_PORT','8883')),keepalive=30)
        client.loop_start()
        if not self.ready.wait(8) or not self.connected:
            self.close();raise TransportUnavailable('Connexion MQTT sécurisée non établie.')

    def send(self,packet):
        if not self.connected:raise TransportUnavailable('Connexion MQTT interrompue.')
        result=self.client.publish('skelivia/v1/devices/skm-001/telemetry',json.dumps(packet,allow_nan=False,separators=(',',':')),qos=1,retain=False)
        if result.rc!=mqtt.MQTT_ERR_SUCCESS:raise TransportUnavailable('Publication MQTT refusée.')
        with self.condition:
            if not self.condition.wait_for(lambda:result.mid in self.acks,timeout=8):raise TransportUnavailable('Accusé MQTT absent ; réception en base non confirmée.')
            accepted=self.acks.pop(result.mid)
        if not accepted:raise TransportUnavailable('Le broker a refusé cette publication.')

    def close(self):
        if self.client:
            self.client.disconnect();self.client.loop_stop();self.client=None
        self.connected=False
