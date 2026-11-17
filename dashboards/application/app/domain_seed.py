"""Explicit, idempotent fixtures. Call only when initializing the synthetic bank."""
import time
from sqlalchemy import select
from .models import Account, CareLink
from .domain_models import DomainRecord, SupportScope


def seed_domain(db):
    if db.get(Account,'t-support'):
        for org in ['atelier-a','soins-a']:
            if not db.get(SupportScope,('t-support',org)):
                db.add(SupportScope(support_id='t-support',org_id=org,active=True))
        db.flush()
    if db.get(DomainRecord, 'domain-seed-v1'):
        return
    now = time.time()
    def add(ident, kind, data, **kw):
        db.add(DomainRecord(id=ident,kind=kind,data=data,created_at=now,updated_at=now,**kw))
    users=list(db.scalars(select(Account).where(Account.role=='user')))
    if not users:
        return
    for user in users:
        suffix=user.id.removeprefix('u-')
        device='demo-device-'+('a' if suffix=='alice' else 'b' if suffix=='benoit' else suffix)
        add(device,'device',{'synthetic':True,'firmware':'2.4.1','connection':'unknown','last_seen':None,'calibration':'C-DEMO-01','calibration_status':'synthetic_reference','history':[],'certificate':{'expires':now+7*86400,'revoked':False,'serial':'SYNTHETIC-'+device}},owner_id=user.id,patient_id=user.patient_id,org_id=user.org_id)
        support=db.scalar(select(Account).where(Account.role=='support',Account.org_id==user.org_id,Account.active.is_(True)))
        add('ticket-'+suffix,'ticket',{'title':'Vérification technique de démonstration','category':'calibration','device_id':device,'messages':[{'author_id':user.id,'body':'Ticket fictif, aucun signal matériel reçu.','at':now}],'diagnostic_expires':0,'checks':{},'synthetic':True},device_id=device,owner_id=user.id,org_id=user.org_id,assigned_to=support.id if support else None,status='in_progress')
    for link in db.scalars(select(CareLink).where(CareLink.enabled.is_(True))):
        add('advice-'+link.id,'document',{'kind':'advice','title':'Réglage du poste — exemple','body':'Conseil fictif de démonstration, à remplacer par un conseil rédigé par le professionnel.','author_id':link.clinician_id,'synthetic':True},owner_id=link.clinician_id,patient_id=link.patient_id,document_id='doc-'+link.id,version=1)
    for org in sorted({u.org_id for u in users}):
        linked=next((u for u in users if u.org_id==org),None)
        relation=db.scalar(select(CareLink).where(CareLink.patient_id==linked.patient_id,CareLink.enabled.is_(True)))
        add('rec-'+org,'recommendation',{'title':'Vérifier les possibilités de réglage du poste','body':'Recommandation organisationnelle fictive, sans donnée individuelle.','category':'layout','history':[{'status':'todo','at':now}]},owner_id=relation.clinician_id if relation else None,org_id=org,status='todo')
    add('patch-demo','patch',{'title':'Firmware de démonstration','version':'2.4.2','priority':'medium','exposure':'À évaluer','tests':'Aucune preuve matérielle disponible.','reason':'Évaluation requise','synthetic':True},status='review')
    add('component-api','component',{'title':'API SKELIVIA','version':'development','end_of_support':'unknown'},status='inventory')
    add('component-mouse','component',{'title':'Logiciel embarqué','version':'2.4.1','end_of_support':'unknown'},status='inventory')
    add('incident-demo','incident',{'title':'Exemple de source de journaux à vérifier','body':'Événement fictif. La présence de ce dossier ne prouve pas une panne réelle.','timeline':[],'synthetic':True},status='review')
    add('backup-state','proof',{'kind':'backup','description':'Aucune sauvegarde exécutée par le domaine. Attente de preuve signée par un adaptateur.','verified':False},status='unknown')
    add('domain-seed-v1','seed',{'synthetic':True},status='complete')
    db.flush()
