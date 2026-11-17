"""The operator proof includes only allowlisted event outcomes, no sensor data."""
import json
from uuid import uuid4
from sqlalchemy import select
from app.ingestion import ingest
from app.domain_models import DomainRecord
from scripts.verify_usage_events import verify
from test_ingestion import bank, commands_bank, packet, usage, NOW, TOPIC


def test_readonly_proof_checks_notification_and_omits_private_values(commands_bank):
    run_id=str(uuid4())
    ingest(commands_bank,TOPIC,packet(session_id=run_id,events=[usage()]),now=NOW)
    with commands_bank() as db:
        proof=verify(db,run_id)
        assert proof['database_receipts']==1 and proof['fixed_synthetic_binding']
        assert proof['notifications_expected']==proof['notifications_verified']==1
        assert proof['events_by_status']=={'notification_created':1}
        rendered=json.dumps(proof)
        assert all(word not in rendered for word in ('contact_seconds','thumb_pct','palm_pct','p-alice','u-alice','title','password','otp'))
        assert not db.new and not db.dirty and not db.deleted


def test_missing_or_mismatched_notification_is_not_claimed_verified(commands_bank):
    run_id=str(uuid4())
    ingest(commands_bank,TOPIC,packet(session_id=run_id,events=[usage()]),now=NOW)
    with commands_bank.begin() as db:
        notice=db.scalar(select(DomainRecord).where(DomainRecord.kind=='notification'))
        notice.owner_id='other'
    with commands_bank() as db:
        proof=verify(db,run_id)
        assert proof['notifications_expected']==1 and proof['notifications_verified']==0
        assert not proof['events'][0]['notification_verified']


def test_absent_run_has_no_vacuous_success(commands_bank):
    with commands_bank() as db:
        proof=verify(db,str(uuid4()))
        assert proof['database_receipts']==0 and not proof['fixed_synthetic_binding']
