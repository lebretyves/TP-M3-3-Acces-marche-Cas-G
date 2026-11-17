from datetime import datetime,timezone
from sqlalchemy import select
from app.database import database
from app.models import Audit
from app.domain_models import DomainRecord
from app.security_monitor import tick,snapshot


def test_failed_login_signal_heartbeat_and_staleness(tmp_path,monkeypatch):
    monkeypatch.setenv('SKELIVIA_DATA_KEY_FILE',str(tmp_path/'key'))
    engine,sessions=database('sqlite:///'+(tmp_path/'monitor.db').as_posix())
    now=1794643200
    with sessions.begin() as db:
        for _ in range(12):db.add(Audit(at=datetime.fromtimestamp(now,timezone.utc).isoformat(),event='connexion_refusee',actor_id='anonyme',result='refus'))
        for i in range(12):db.add(DomainRecord(id='deny-'+str(i),kind='audit',status='active',created_at=now,updated_at=now,data={'action':'denied.document.publish','actor_id':'test','target_id':'test'}))
    tick(sessions,True,now)
    tick(sessions,True,now+5)
    with sessions() as db:
        rows=list(db.scalars(select(DomainRecord).where(DomainRecord.kind=='incident')))
        assert len(rows)==2 and {r.data['source'] for r in rows}=={'authentication','authorization'}
        assert snapshot(db,now+10)['status']=='connected'
        assert snapshot(db,now+100)['status']=='stale'
    engine.dispose()
