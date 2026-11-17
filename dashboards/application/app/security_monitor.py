"""Operational signals from this service, never inferred from patient measurements."""
from datetime import datetime,timezone
import time
from sqlalchemy import Float,String,select,func
from sqlalchemy.orm import Mapped,mapped_column
from .models import Base,Audit
from .domain_models import DomainRecord


class ServiceHeartbeat(Base):
    __tablename__='service_heartbeats'
    id: Mapped[str]=mapped_column(String(40),primary_key=True)
    last_seen: Mapped[float]=mapped_column(Float)
    state: Mapped[str]=mapped_column(String(30))


def tick(sessions,connected,now=None):
    now=time.time() if now is None else now
    cutoff=datetime.fromtimestamp(now-600,timezone.utc).isoformat()
    with sessions.begin() as db:
        heartbeat=db.get(ServiceHeartbeat,'ingestion')
        if not heartbeat:
            heartbeat=ServiceHeartbeat(id='ingestion',last_seen=now,state='connected' if connected else 'disconnected');db.add(heartbeat)
        else: heartbeat.last_seen=now;heartbeat.state='connected' if connected else 'disconnected'
        count=db.scalar(select(func.count()).select_from(Audit).where(Audit.at>=cutoff,Audit.event.in_(['connexion_refusee','oidc_refusee'])))
        key='auth-rate-'+str(int(now//600))
        if count>=12 and not db.get(DomainRecord,key):
            db.add(DomainRecord(id=key,kind='incident',status='review',created_at=now,updated_at=now,data={'title':'Échecs de connexion répétés','body':'Au moins douze authentifications ont été refusées sur dix minutes. À qualifier ; ce signal seul ne confirme pas une intrusion.','timeline':[],'source':'authentication','synthetic':False}))
        events=db.scalars(select(DomainRecord).where(DomainRecord.kind=='audit',DomainRecord.created_at>=now-600).order_by(DomainRecord.created_at.desc()).limit(1000))
        denied=sum(str(event.data.get('action','')).startswith('denied.') for event in events)
        denied_key='access-denied-'+str(int(now//600))
        if denied>=12 and not db.get(DomainRecord,denied_key):
            db.add(DomainRecord(id=denied_key,kind='incident',status='review',created_at=now,updated_at=now,data={'title':'Actions interdites répétées','body':'Au moins douze actions métier ont été refusées sur dix minutes. Examiner les événements techniques avant de qualifier un incident.','timeline':[],'source':'authorization','synthetic':False}))


def snapshot(db,now=None):
    now=time.time() if now is None else now
    row=db.get(ServiceHeartbeat,'ingestion')
    return {'service':'Ingestion et surveillance des connexions','status':'unknown' if not row else 'stale' if now-row.last_seen>90 else row.state,'last_seen':datetime.fromtimestamp(row.last_seen,timezone.utc).isoformat() if row else None,'scope':'Disponibilité du worker et lien MQTT ; ce signal ne prouve pas la couverture de tous les journaux.'}
