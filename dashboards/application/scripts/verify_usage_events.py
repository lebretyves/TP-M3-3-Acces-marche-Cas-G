"""Offline, read-only proof of one fixed synthetic simulator run.

Run inside the migrate service: python -m scripts.verify_usage_events --run UUID.
Prints receipt/event/notification verification only, never measurement values,
account names, notification titles, database URLs, secrets or exception details.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from uuid import UUID
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.database import runtime_url
from app.domain_models import DomainRecord
from app.models import Report
from app.transport_models import IngestReceipt

DEVICE = 'demo-device-a'
KINDS = {'pause_reminder','high_force','quiet_contact','absent'}
STATUSES = {'notification_created','cooldown','pause_disabled','pause_snoozed','owner_unavailable'}


def verify(db, run_id):
    run_id = str(UUID(run_id))
    rows = db.execute(select(IngestReceipt.sequence, Report).join(Report, Report.id == IngestReceipt.report_id)
        .where(IngestReceipt.device_id == DEVICE, IngestReceipt.session_id == run_id)
        .order_by(IngestReceipt.sequence).limit(61)).all()
    if len(rows) > 60:
        raise ValueError('Receipt bound exceeded')
    results = []
    bindings_ok = bool(rows) and all(report.synthetic is True and report.patient_id == 'p-alice' for _,report in rows)
    for sequence, report in rows:
        events = report.metrics.get('usage_events', [])
        if not isinstance(events,list) or len(events) > 4:
            raise ValueError('Invalid event proof')
        for event in events:
            if event.get('kind') not in KINDS or event.get('status') not in STATUSES or event.get('origin') not in {'computed','manual'} or event.get('synthetic') is not True:
                raise ValueError('Invalid event proof')
            result = {'sequence':sequence, 'kind':event['kind'], 'origin':event['origin'], 'status':event['status']}
            if event['status'] == 'notification_created':
                notice_id = event.get('notification_id')
                if not isinstance(notice_id,str) or not notice_id.startswith('usage-') or len(notice_id) > 80:
                    raise ValueError('Invalid notification proof')
                notice = db.get(DomainRecord, notice_id)
                result['notification_verified'] = bool(notice and notice.kind == 'notification' and notice.owner_id == 'u-alice' and notice.device_id == DEVICE
                    and notice.data.get('synthetic') is True and notice.data.get('event_kind') == event['kind'] and notice.data.get('origin') == event['origin']
                    and notice.data.get('simulation_run') == run_id and notice.data.get('sequence') == sequence
                    and notice.data.get('kind') == ('pause' if event['kind'] == 'pause_reminder' else 'usage'))
            results.append(result)
    created = [result for result in results if result['status'] == 'notification_created']
    return {'run_id':run_id,'device_id':DEVICE,'verified_at':datetime.now(timezone.utc).isoformat(),
        'database_receipts':len(rows), 'fixed_synthetic_binding':bindings_ok,
        'events_by_kind':dict(Counter(result['kind'] for result in results)),
        'events_by_status':dict(Counter(result['status'] for result in results)),
        'notifications_expected':len(created),
        'notifications_verified':sum(result['notification_verified'] for result in created),
        'events':results, 'scope':'database_only_not_external_delivery'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    engine = None
    try:
        run_id = str(UUID(args.run))
        url = runtime_url()
        if url.drivername != 'postgresql+psycopg':
            raise ValueError('Offline PostgreSQL operator required')
        engine = create_engine(url, hide_parameters=True, connect_args={'connect_timeout':5})
        with engine.connect() as connection:
            with connection.begin():
                connection.execute(text('SET TRANSACTION READ ONLY'))
                if connection.execute(text('SELECT current_user')).scalar_one() != 'skelivia_owner':
                    raise ValueError('Offline migration role required')
                with Session(bind=connection) as db:
                    proof = verify(db, run_id)
        print(json.dumps(proof, ensure_ascii=False))
        return 0 if proof['fixed_synthetic_binding'] and proof['notifications_expected'] == proof['notifications_verified'] else 1
    except Exception:
        print(json.dumps({'error':'verification_refused','detail':'Vérification indisponible ; aucun contenu privé ni détail de connexion publié.'},ensure_ascii=False))
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
