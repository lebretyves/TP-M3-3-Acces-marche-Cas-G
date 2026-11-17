"""Préparer/migrer uniquement le banc fictif dédié P2 ; aucune remise à zéro."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import hashlib
import json
import secrets
import sqlite3
import socket
import psycopg
from psycopg import sql
from sqlalchemy import create_engine,select,func
from sqlalchemy.engine import URL
from .database import ROOT
from .models import Base

RUNTIME=ROOT/'.runtime/postgres'
PORT=55432


def require_stopped_bank():
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1',8766))==0:
            raise RuntimeError('Arrêter le serveur P2 sur 8766 avant migration ou activation.')


def content_digest(rows):
    canonical=sorted(json.dumps(dict(row),sort_keys=True,ensure_ascii=False) for row in rows)
    return hashlib.sha256(json.dumps(canonical,ensure_ascii=False).encode('utf-8')).hexdigest()


def initialize_secrets():
    RUNTIME.mkdir(parents=True,exist_ok=True)
    path=RUNTIME/'credentials.json'
    if path.exists():
        if not (RUNTIME/'admin.password').exists():
            raise RuntimeError('Fichier administrateur manquant ; ne pas changer les secrets d’un volume existant.')
        print('Secrets locaux existants conservés.')
        return
    if (RUNTIME/'admin.password').exists():raise RuntimeError('Préparation partielle : vérifier les fichiers avant reprise.')
    data={'admin_password':secrets.token_urlsafe(36),'app_password':secrets.token_urlsafe(36)}
    path.write_text(json.dumps(data,indent=2),encoding='utf-8')
    (RUNTIME/'admin.password').write_text(data['admin_password'],encoding='utf-8')
    print('Secrets PostgreSQL générés dans .runtime, exclus de Git.')


def credentials():return json.loads((RUNTIME/'credentials.json').read_text(encoding='utf-8'))


def pg_url(*,admin=False,database='p2',schema=None):
    data=credentials()
    url=URL.create('postgresql+psycopg',username='p2_bootstrap' if admin else 'p2_app',password=data['admin_password' if admin else 'app_password'],host='127.0.0.1',port=PORT,database=database)
    if schema:
        if not schema.startswith('p2test_') or not schema.replace('_','').isalnum():raise ValueError('Schéma de test invalide')
        url=url.update_query_dict({'options':'-csearch_path='+schema})
    return url


def admin_connection(database='p2'):
    return psycopg.connect(host='127.0.0.1',port=PORT,dbname=database,user='p2_bootstrap',password=credentials()['admin_password'],connect_timeout=5,autocommit=True)


def grant_schema(conn,schema='public'):
    # Le rôle applicatif ne possède ni schéma ni table ; aucune capacité DDL.
    s=sql.Identifier(schema)
    conn.execute(sql.SQL('REVOKE ALL ON SCHEMA {} FROM PUBLIC').format(s))
    conn.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO p2_app').format(s))
    conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {} TO p2_app').format(s))
    conn.execute(sql.SQL('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {} TO p2_app').format(s))


def configure():
    with admin_connection() as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='p2_app'").fetchone():
            conn.execute(sql.SQL('CREATE ROLE p2_app LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Literal(credentials()['app_password'])))
        for name in ['p2','p2_test']:
            if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
                conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO p2_app').format(sql.Identifier(name)))
    engine=create_engine(pg_url(admin=True),hide_parameters=True)
    Base.metadata.create_all(engine);engine.dispose()
    with admin_connection() as conn:grant_schema(conn)
    with admin_connection('p2_test') as conn:
        conn.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
    print('Bases P2 créées ; p2_app limité au traitement, sans privilèges administrateur.')


def migrate():
    require_stopped_bank()
    source=ROOT/'.runtime/p2.db'
    if not source.exists():raise RuntimeError('Base SQLite source absente.')
    now=datetime.now(timezone.utc)
    backup=RUNTIME/('p2_sqlite_avant_migration_'+now.strftime('%Y%m%dT%H%M%SZ')+'.db')
    with sqlite3.connect(source) as src,sqlite3.connect(backup) as dst:src.backup(dst)
    old=create_engine('sqlite:///'+backup.as_posix(),hide_parameters=True)
    new=create_engine(pg_url(admin=True),hide_parameters=True)
    counts={};digests={}
    excluded={'web_sessions','login_limits'}
    # Refus d'écrasement : la destination doit être entièrement vide.
    with new.begin() as dst,old.connect() as src:
        for table in Base.metadata.sorted_tables:
            if dst.scalar(select(func.count()).select_from(table)):
                raise RuntimeError('Destination non vide : migration arrêtée sans écrasement.')
        for table in Base.metadata.sorted_tables:
            if table.name in excluded:continue
            rows=[dict(r) for r in src.execute(select(table)).mappings()]
            if table.name=='reports' and any(r['synthetic'] is not True for r in rows):raise RuntimeError('La source doit contenir uniquement des bilans fictifs.')
            if rows:dst.execute(table.insert(),rows)
            counts[table.name]=len(rows)
            # Vérifier les valeurs complètes, y compris droits, expirations et données.
            after=[dict(r) for r in dst.execute(select(table)).mappings()]
            digests[table.name]=content_digest(rows)
            if digests[table.name]!=content_digest(after):raise RuntimeError('Différence de contenu pendant la migration.')
    with admin_connection() as conn:
        conn.execute("SELECT setval(pg_get_serial_sequence('audit','id'), COALESCE((SELECT MAX(id) FROM audit),0)+1, false)")
    old.dispose();new.dispose()
    proof={'status':'COPIE_VERIFIEE_NON_ACTIVEE','utc':now.isoformat(),'counts':counts,'digests':digests,'excluded_tables':sorted(excluded),'excluded_reason':'Sessions invalidées à la bascule ; limites de connexion du banc remises à zéro.','source_backup':backup.name,'source_sha256':hashlib.sha256(backup.read_bytes()).hexdigest()}
    (RUNTIME/'migration.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in proof.items() if k not in ['source_backup']},ensure_ascii=False))


def activate():
    require_stopped_bank()
    proof=json.loads((RUNTIME/'migration.json').read_text(encoding='utf-8'))
    if proof['status']!='COPIE_VERIFIEE_NON_ACTIVEE':raise RuntimeError('Migration non vérifiée.')
    engine=create_engine(pg_url(),hide_parameters=True,connect_args={'connect_timeout':5})
    source=create_engine('sqlite:///'+(ROOT/'.runtime/p2.db').as_posix(),hide_parameters=True)
    with engine.connect() as conn,source.connect() as original:
        roles=conn.exec_driver_sql("SELECT current_user,rolsuper,rolcreatedb,rolcreaterole,rolbypassrls FROM pg_roles WHERE rolname=current_user").one()
        if roles[0]!='p2_app' or any(roles[1:]):raise RuntimeError('Privilèges applicatifs excessifs.')
        for table in Base.metadata.sorted_tables:
            if table.name in proof['counts']:
                expected=proof['digests'][table.name]
                if content_digest(conn.execute(select(table)).mappings())!=expected:
                    raise RuntimeError('Contenu PostgreSQL modifié avant activation.')
                if content_digest(original.execute(select(table)).mappings())!=expected:
                    raise RuntimeError('Source SQLite modifiée depuis la copie ; activation refusée.')
    engine.dispose();source.dispose()
    config=ROOT/'.runtime/database.json'
    if config.exists():raise RuntimeError('Configuration déjà présente : activation automatique refusée.')
    config.write_text(json.dumps({'backend':'postgresql','activated_at':datetime.now(timezone.utc).isoformat(),'migration':'postgres/migration.json'},indent=2),encoding='utf-8')
    print('PostgreSQL sélectionné au prochain démarrage ; aucun repli SQLite implicite.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','configure','migrate','activate'])
    action=parser.parse_args().action
    {'prepare':initialize_secrets,'configure':configure,'migrate':migrate,'activate':activate}[action]()
