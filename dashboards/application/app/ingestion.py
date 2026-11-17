"""Strict synthetic v1 ingestion. Call only from the authenticated broker worker.

The publisher CN is bound to the topic by broker ACL, never trusted from JSON.
No sensor readings or payloads are written to application logs.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
import re
from typing import Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import Report
from .transport_models import DeviceIdentity, IngestCursor, IngestDeviceCursor, IngestReceipt

TOPIC = re.compile(r'^skelivia/v1/devices/([A-Za-z0-9_-]{1,80})/telemetry$')


class IngestionRejected(ValueError):
    """A stable non-sensitive rejection reason; contains no payload values."""


class MetricsV1(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    contact_seconds: float = Field(ge=0, le=3600)
    episodes: int = Field(ge=0, le=100000)
    thumb_pct: float = Field(ge=0, le=100)
    palm_pct: float = Field(ge=0, le=100)


class UsageEventV1(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    kind: Literal['pause_reminder', 'high_force', 'quiet_contact', 'absent']
    at_seconds: float = Field(ge=0, le=3600)
    origin: Literal['computed', 'manual']


class EnvelopeV1(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, allow_inf_nan=False)
    schema_version: Literal['skelivia.telemetry.v1']
    synthetic: StrictBool
    device_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    session_id: str
    sequence: int = Field(ge=0, le=2147483647)
    measured_at: str
    window_start: str
    firmware_version: str = Field(pattern=r'^[A-Za-z0-9._-]{1,40}$')
    algorithm_version: str = Field(pattern=r'^[A-Za-z0-9._-]{1,40}$')
    calibration_version: str = Field(pattern=r'^[A-Za-z0-9._-]{1,40}$')
    quality: Literal['valid', 'calibration_required', 'invalid']
    metrics: MetricsV1 | None
    events: list[UsageEventV1] = Field(default_factory=list, max_length=4)

    @field_validator('synthetic')
    @classmethod
    def only_synthetic(cls, value):
        if value is not True:
            raise ValueError('real_data_forbidden')
        return value

    @field_validator('session_id')
    @classmethod
    def canonical_uuid(cls, value):
        if str(UUID(value)) != value:
            raise ValueError('noncanonical_session')
        return value

    @field_validator('measured_at','window_start')
    @classmethod
    def aware_time(cls, value):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
            raise ValueError('utc_required')
        return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def ingest(session_factory, topic: str, payload: bytes, *, retained=False, now=None):
    """Commit receipt, cursor and derived report atomically; duplicate delivery is rejected."""
    if retained:
        raise IngestionRejected('retained_forbidden')
    match = TOPIC.fullmatch(topic)
    if not match or not payload or len(payload) > 16384:
        raise IngestionRejected('invalid_transport')
    try:
        data = json.loads(payload, object_pairs_hook=_unique_object)
        packet = EnvelopeV1.model_validate(data)
    except (ValidationError, ValueError, UnicodeError, TypeError):
        raise IngestionRejected('invalid_schema') from None
    now = now or datetime.now(timezone.utc)
    measured = datetime.fromisoformat(packet.measured_at.replace('Z', '+00:00'))
    window_start = datetime.fromisoformat(packet.window_start.replace('Z', '+00:00'))
    duration=(measured-window_start).total_seconds()
    if not 0<duration<=3600 or (packet.metrics and packet.metrics.contact_seconds>duration):
        raise IngestionRejected('invalid_interval')
    age = (now - measured).total_seconds()
    if age > 120 or age < -30:
        raise IngestionRejected('stale_or_future')
    if (packet.quality == 'valid') != (packet.metrics is not None):
        raise IngestionRejected('quality_metrics_mismatch')
    if packet.events and (packet.quality != 'valid' or any(event.at_seconds > duration for event in packet.events) or len({event.kind for event in packet.events}) != len(packet.events)):
        raise IngestionRejected('invalid_usage_events')
    # This import is delayed to keep schema validation independently testable.
    from .domain_models import DomainRecord
    try:
        with session_factory.begin() as db:
            identity = db.scalar(select(DeviceIdentity).where(DeviceIdentity.cert_cn == match[1]))
            if not identity or identity.revoked_at is not None or identity.device_id != packet.device_id or (identity.expires_at is not None and identity.expires_at <= now.timestamp()):
                raise IngestionRejected('identity_forbidden')
            device = db.scalar(select(DomainRecord).where(DomainRecord.id == identity.device_id, DomainRecord.kind == 'device').with_for_update())
            if not device or not device.patient_id or device.status in ('revoked', 'lost', 'replaced', 'deleted'):
                raise IngestionRejected('device_forbidden')
            meta = device.data or {}
            cert = meta.get('certificate', {})
            if cert.get('revoked') or (cert.get('serial') and cert['serial'] != identity.cert_serial):
                raise IngestionRejected('certificate_revoked_or_rotated')
            if packet.quality == 'valid' and (meta.get('calibration') != packet.calibration_version or meta.get('calibration_status') not in ('valid', 'verified', 'réussie', 'verified_local', 'synthetic_reference')):
                raise IngestionRejected('calibration_mismatch')
            cursor_id = identity.device_id + ':' + packet.session_id
            cursor = db.get(IngestCursor, cursor_id)
            if cursor and (packet.sequence <= cursor.last_sequence or measured.timestamp() < cursor.last_measured_at):
                raise IngestionRejected('replay_or_out_of_order')
            global_cursor=db.get(IngestDeviceCursor,identity.device_id)
            if global_cursor and window_start.timestamp()<global_cursor.last_window_end:
                raise IngestionRejected('overlapping_interval')
            if global_cursor:
                global_cursor.last_window_end=measured.timestamp()
            else:
                db.add(IngestDeviceCursor(device_id=identity.device_id,last_window_end=measured.timestamp()))
            if not cursor:
                cursor = IngestCursor(id=cursor_id, device_id=identity.device_id, session_id=packet.session_id, last_sequence=packet.sequence, last_measured_at=measured.timestamp())
                db.add(cursor)
            else:
                cursor.last_sequence = packet.sequence
                cursor.last_measured_at = measured.timestamp()
            report_id = 'ingest-' + uuid4().hex
            metrics = packet.metrics.model_dump() if packet.metrics else {}
            metrics.update(calibration=packet.calibration_version, firmware_version=packet.firmware_version, algorithm_version=packet.algorithm_version, device_id=identity.device_id, source='synthetic_mtls_v1', received_at=now.isoformat(),window_start=window_start.isoformat(),window_end=measured.isoformat(),window_duration_seconds=duration)
            if packet.events:
                from .usage_events import record_usage_events
                metrics['usage_events'] = record_usage_events(db, device, packet.events, now.timestamp(), simulation_run=packet.session_id, sequence=packet.sequence)
            db.add(Report(id=report_id, patient_id=device.patient_id, title='Mesures du banc synthétique', recorded_at=measured.isoformat(), quality=packet.quality, metrics=metrics, synthetic=True))
            db.add(IngestReceipt(id=uuid4().hex, device_id=identity.device_id, session_id=packet.session_id, sequence=packet.sequence, measured_at=measured.timestamp(), received_at=now.timestamp(), payload_digest=sha256(payload).hexdigest(), report_id=report_id))
            device.data = {**device.data, 'last_seen': now.isoformat(), 'last_quality':packet.quality, 'connection': 'connected'}
        return report_id
    except IntegrityError:
        raise IngestionRejected('duplicate_or_conflict') from None

