"""Authenticated encryption of sensitive payloads; keys never enter the database."""
import base64
import json
import os
import secrets
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator


def data_key():
    path = Path(os.environ.get('SKELIVIA_DATA_KEY_FILE', str(Path(__file__).resolve().parents[1]/'.runtime/data.key')))
    if not path.exists():
        if os.environ.get('SKELIVIA_AUTH_MODE', 'local') != 'local':
            raise RuntimeError('Data encryption key is required; no generated replacement permitted.')
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(base64.b64encode(secrets.token_bytes(32)))
        except FileExistsError:
            pass
    key = base64.b64decode(path.read_bytes().strip(), validate=True)
    if len(key) != 32:
        raise RuntimeError('Invalid data encryption key.')
    return key


class SensitiveJSON(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        nonce = secrets.token_bytes(12)
        payload = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
        encrypted = AESGCM(data_key()).encrypt(nonce, payload, b'skelivia-json-v1')
        return 'v1:' + base64.b64encode(nonce + encrypted).decode('ascii')

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if not value.startswith('v1:'):
            raise ValueError('Unencrypted sensitive payload refused.')
        raw = base64.b64decode(value[3:], validate=True)
        return json.loads(AESGCM(data_key()).decrypt(raw[:12], raw[12:], b'skelivia-json-v1'))
