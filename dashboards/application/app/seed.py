"""Initialisation explicite du banc, jamais appelée par une requête web."""
from datetime import datetime, timezone
import json
import secrets
import pyotp
from argon2 import PasswordHasher
from sqlalchemy import select
from .database import ROOT, database
from .models import Account, Alert, CareLink, Prevention, Report, Ticket

DEMO_ACCOUNTS = [
    ('u-alice','alice.demo','Alice · utilisatrice fictive','user','atelier-a','p-alice'),
    ('u-benoit','benoit.demo','Benoît · utilisateur fictif','user','atelier-b','p-benoit'),
    ('c-lina','lina.demo','Dr Lina · soignante fictive','clinician','soins-a',None),
    ('c-marc','marc.demo','Dr Marc · soignant fictif','clinician','soins-b',None),
    ('e-atelier','prevention.demo','Camille · prévention','employer','atelier-a',None),
    ('t-support','support.demo','Noé · support technique','support','atelier-a',None),
    ('s-securite','securite.demo','Sam · administration sécurité','security','interne',None),
    ('s-approbateur','approbateur.demo','Alex · approbateur sécurité','security','interne',None),
]


def seed(factory):
    ph = PasswordHasher()
    credentials = []
    with factory() as db:
        from .domain_models import DomainRecord
        retired=set(db.scalars(select(DomainRecord.owner_id).where(DomainRecord.kind=='deletion',DomainRecord.status=='completed')))
        existing=set(db.scalars(select(Account.id)))
        for ident,username,name,role,org,patient in DEMO_ACCOUNTS:
            if ident in existing or ident in retired:
                continue
            password=secrets.token_urlsafe(18)
            otp=pyotp.random_base32()
            db.add(Account(id=ident,username=username,name=name,role=role,org_id=org,patient_id=patient,password_hash=ph.hash(password),otp_secret=otp))
            credentials.append({'username':username,'password':password,'otp_secret':otp,'name':name})
        if existing or retired:
            db.commit()
            return credentials
        db.add_all([CareLink(id='link-a',patient_id='p-alice',clinician_id='c-lina'),CareLink(id='link-b',patient_id='p-benoit',clinician_id='c-marc')])
        recorded=datetime.now(timezone.utc).isoformat()
        db.add_all([
            Report(id='r-alice-01',patient_id='p-alice',title='Séquence de travail fictive',recorded_at=recorded,quality='valid',metrics={'contact_seconds':180,'episodes':12,'thumb_pct':42,'palm_pct':31}),
            Report(id='r-alice-02',patient_id='p-alice',title='Exemple de canal indisponible',recorded_at=recorded,quality='invalid',metrics={'contact_seconds':60,'episodes':3,'thumb_pct':None,'palm_pct':28}),
            Report(id='r-benoit-01',patient_id='p-benoit',title='Séquence fictive indépendante',recorded_at=recorded,quality='valid',metrics={'contact_seconds':240,'episodes':8,'thumb_pct':36,'palm_pct':22}),
            Alert(id='a-alice-01',patient_id='p-alice',kind='usage',message='Exemple de rappel : relâcher la prise si nécessaire. Aucun diagnostic.'),
            Alert(id='a-alice-02',patient_id='p-alice',kind='technical',message='Exemple de défaut : appui pouce indisponible dans le second bilan.'),
            Alert(id='a-benoit-01',patient_id='p-benoit',kind='usage',message='Exemple fictif de rappel de mouvement.'),
            Ticket(id='t-alice-01',user_id='u-alice',org_id='atelier-a',device_id='demo-device-a',category='connexion'),
            Ticket(id='t-benoit-01',user_id='u-benoit',org_id='atelier-b',device_id='demo-device-b',category='capteur'),
            Prevention(id='pr-a-01',org_id='atelier-a',title='Organiser une présentation des réglages du poste'),
            Prevention(id='pr-a-02',org_id='atelier-a',title='Prévoir des interruptions d’activité dans l’organisation'),
            Prevention(id='pr-b-01',org_id='atelier-b',title='Action organisationnelle du second atelier'),
        ])
        db.commit()
    return credentials


def main():
    _, factory=database()
    credentials=seed(factory)
    from .domain_seed import seed_domain
    with factory() as db:
        seed_domain(db)
        db.commit()
    if not credentials:
        print('Banc déjà initialisé ; aucune donnée ni identité remplacée.')
        return
    runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
    (runtime/'comptes_locaux.json').write_text(json.dumps(credentials,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['P2 - ACCES AU BANC LOCAL FICTIF','Ouvrir http://127.0.0.1:8772','Identifiants personnels au banc : ne pas déposer ce fichier sur Git ni Teams.','Pour un code temporaire : lancer codes_connexion.ps1, ou enregistrer la clé TOTP dans une application d’authentification.','Les codes générés sur le même PC servent aux tests ; ils ne prouvent pas l’indépendance de deux facteurs en production.','']
    for c in credentials:
        lines.extend([c['name'], 'Identifiant : '+c['username'],'Mot de passe : '+c['password'],'Clé TOTP pour authentificateur : '+c['otp_secret'],''])
    (runtime/'ACCES_LOCAL.txt').write_text('\n'.join(lines),encoding='utf-8')
    print('8 comptes fictifs créés. Identifiants conservés uniquement dans .runtime/ACCES_LOCAL.txt (exclu de Git).')


if __name__=='__main__': main()
