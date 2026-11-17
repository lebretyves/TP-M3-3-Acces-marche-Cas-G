"""Synthetic usage events, bound to the device owner inside ingestion's transaction.

The device row is already locked. Receipt/cursor checks run before this function;
notifications, anti-spam timestamps and measurements therefore commit together.
No medical interpretation, recipient supplied by a publisher, or external I/O.
"""
from uuid import uuid4
from sqlalchemy import select
from .models import Account
from .domain_models import DomainRecord

COOLDOWN_SECONDS = 60
TITLES = {
    'pause_reminder': 'rappel de pause lié à une utilisation intensive.',
    'high_force': 'appui relatif élevé.',
    'quiet_contact': 'contact sans mouvement.',
    'absent': 'absence de contact.',
}


def record_usage_events(db, device, events, now, *, simulation_run=None, sequence=None):
    # Column selection matches the worker's minimal account grants. Identity and
    # recipient are taken from the registered device, never from event JSON.
    owner = db.execute(select(Account.id, Account.active, Account.role).where(Account.id == device.owner_id)).first()
    eligible = bool(owner and owner.active and owner.role == 'user')
    settings_row = db.scalar(select(DomainRecord).where(DomainRecord.kind == 'settings', DomainRecord.owner_id == device.owner_id).order_by(DomainRecord.updated_at.desc()).limit(1)) if eligible else None
    settings = settings_row.data if settings_row else {}
    last_sent = dict(device.data.get('usage_notice_times', {}))
    results = []
    for event in events:
        result = {**event.model_dump(), 'synthetic': True}
        if not eligible:
            result['status'] = 'owner_unavailable'
        elif event.kind == 'pause_reminder' and not settings.get('pause_enabled', False):
            result['status'] = 'pause_disabled'
        elif event.kind == 'pause_reminder' and settings.get('snoozed_until', 0) > now:
            result['status'] = 'pause_snoozed'
        elif event.kind in last_sent and now - last_sent[event.kind] < COOLDOWN_SECONDS:
            result['status'] = 'cooldown'
        else:
            # Only pause belongs to the already approved external push channel.
            # The dispatcher rechecks channels, quiet hours, snooze and opt-in.
            notice_id = 'usage-' + uuid4().hex
            db.add(DomainRecord(id=notice_id, kind='notification', owner_id=device.owner_id,
                device_id=device.id, status='active', created_at=now, updated_at=now,
                data={'kind':'pause' if event.kind == 'pause_reminder' else 'usage',
                      'title':('Simulation manuelle : ' if event.origin == 'manual' else 'Simulation : ') + TITLES[event.kind], 'route':'measures', 'read':False,
                      'synthetic':True, 'event_kind':event.kind, 'origin':event.origin,
                      'simulation_run':simulation_run, 'sequence':sequence}))
            last_sent[event.kind] = now
            result.update(status='notification_created', notification_id=notice_id)
        results.append(result)
    device.data = {**device.data, 'usage_notice_times':last_sent}
    return results
