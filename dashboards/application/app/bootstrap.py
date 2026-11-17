"""Explicit schema bootstrap under the migration identity, never in HTTP requests."""
import json
import os
from pathlib import Path
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import sessionmaker
from .database import runtime_url, register_models
from .models import Base, OIDCIdentity, Account
from .seed import seed
from .domain_seed import seed_domain


def install_policies(connection):
    actor="nullif(current_setting('skelivia.actor',true),'')"
    role="nullif(current_setting('skelivia.role',true),'')"
    patient="nullif(current_setting('skelivia.patient',true),'')"
    org="nullif(current_setting('skelivia.org',true),'')"
    security=f"{role}='security'"
    linked="EXISTS (SELECT 1 FROM care_links cl WHERE cl.patient_id={patient_column} AND cl.clinician_id="+actor+" AND cl.enabled)"
    shared="EXISTS (SELECT 1 FROM domain_grants dg WHERE dg.patient_id={patient_column} AND dg.clinician_id="+actor+" AND dg.active AND dg.expires>extract(epoch from now()))"
    medical=lambda column: f"(({role}='user' AND {column}={patient}) OR ({role}='clinician' AND {linked.format(patient_column=column)} AND {shared.format(patient_column=column)}))"
    scope=f"EXISTS (SELECT 1 FROM support_scopes ss WHERE ss.support_id={actor} AND ss.org_id=domain_records.org_id AND ss.active)"
    device=f"EXISTS (SELECT 1 FROM domain_diagnostics dd JOIN accounts da ON da.id=dd.owner_id JOIN support_scopes ds ON ds.support_id=dd.support_id AND ds.org_id=da.org_id AND ds.active WHERE dd.device_id=domain_records.id AND dd.support_id={actor} AND dd.active AND dd.expires>extract(epoch from now()))"
    read_records=f"""(
      (kind='document' AND {medical('domain_records.patient_id')}) OR
      (kind='device' AND (({role}='user' AND owner_id={actor}) OR {security} OR ({role}='support' AND {device}))) OR
      (kind='ticket' AND (({role} IN ('user','clinician') AND owner_id={actor}) OR ({role}='support' AND assigned_to={actor} AND {scope}))) OR
      (kind IN ('settings','notification','reminder') AND owner_id={actor}) OR
      (kind='recommendation' AND (({role}='clinician' AND owner_id={actor}) OR ({role}='employer' AND org_id={org}))) OR
      (kind='deletion' AND (owner_id={actor} OR {security})) OR
      (kind IN ('incident','patch','component','proof','audit','account_request') AND {security}) OR
      (kind='patch' AND {role} IN ('support','clinician') AND status='approved')
    )"""
    insert_records=f"""(
      (kind='document' AND {role}='clinician' AND owner_id={actor} AND {medical('domain_records.patient_id')}) OR
      (kind='ticket' AND {role} IN ('user','clinician') AND owner_id={actor}) OR
      (kind IN ('settings','reminder') AND owner_id={actor}) OR
      (kind IN ('notification','audit') AND {actor} IS NOT NULL) OR
      (kind='recommendation' AND {role}='clinician' AND owner_id={actor}) OR
      (kind='incident' AND {role} IN ('user','clinician','support','security')) OR
      (kind='deletion' AND {role}='user' AND owner_id={actor}) OR
      (kind IN ('patch','component','proof','account_request') AND {security})
    )"""
    update_records=f"({read_records}) AND kind NOT IN ('document','audit')"
    report_read=f"({medical('reports.patient_id')}) AND ( {role}='user' OR EXISTS (SELECT 1 FROM domain_grants dg WHERE dg.patient_id=reports.patient_id AND dg.clinician_id={actor} AND dg.active AND dg.expires>extract(epoch from now()) AND substring(reports.recorded_at,1,10)>=dg.start AND substring(reports.recorded_at,1,10)<=dg.end))"
    grant_read=f"owner_id={actor} OR clinician_id={actor} OR {security}"
    grant_write=f"{role}='user' AND owner_id={actor} AND patient_id={patient}"
    job_read=f"owner_id={actor} OR assigned_to={actor} OR {security}"
    policies={
      'domain_records':{'SELECT':read_records,'INSERT':insert_records,'UPDATE':update_records},
      'domain_grants':{'SELECT':grant_read,'INSERT':grant_write,'UPDATE':grant_write},
      'domain_diagnostics':{'SELECT':f"owner_id={actor} OR support_id={actor} OR {security}",'INSERT':f"owner_id={actor}",'UPDATE':f"owner_id={actor} OR support_id={actor} OR {security}"},
      'domain_jobs':{'SELECT':job_read,'INSERT':f"owner_id={actor} OR {security} OR ({role}='support' AND assigned_to={actor} AND EXISTS (SELECT 1 FROM domain_records jt WHERE jt.kind='ticket' AND (jt.id=domain_jobs.target_id OR (jt.device_id=domain_jobs.target_id AND EXISTS (SELECT 1 FROM domain_diagnostics jd WHERE jd.ticket_id=jt.id AND jd.active AND jd.expires>extract(epoch from now())))) AND jt.assigned_to={actor} AND jt.owner_id=domain_jobs.owner_id))",'UPDATE':job_read},
      'reports':{'SELECT':report_read},
      'service_heartbeats':{'SELECT':security},
      'push_subscriptions':{'SELECT':f'owner_id={actor}','INSERT':f'owner_id={actor}','UPDATE':f'owner_id={actor}'},
      'push_deliveries':{'SELECT':f'owner_id={actor}'},
    }
    for table,rules in policies.items():
        connection.execute(text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
        connection.execute(text(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY'))
        for command,expression in rules.items():
            name=f'app_{command.lower()}'
            connection.execute(text(f'DROP POLICY IF EXISTS {name} ON {table}'))
            clause=f'WITH CHECK ({expression})' if command=='INSERT' else f'USING ({expression})'
            if command=='UPDATE': clause+=f' WITH CHECK ({expression})'
            connection.execute(text(f'CREATE POLICY {name} ON {table} FOR {command} TO skelivia_app {clause}'))
        # Migration identity can seed and upgrade while FORCE RLS protects other connections.
        connection.execute(text(f'DROP POLICY IF EXISTS schema_owner ON {table}'))
        connection.execute(text(f'CREATE POLICY schema_owner ON {table} TO skelivia_owner USING (true) WITH CHECK (true)'))
    for table,commands,expression in [
        ('domain_records',['SELECT','UPDATE'],"kind='device'"),
        ('domain_jobs',['SELECT','UPDATE'],"kind IN ('calibration','update')"),
        ('reports',['INSERT'],"synthetic=true"),
    ]:
        for command in commands:
            name='worker_'+command.lower()
            connection.execute(text(f'DROP POLICY IF EXISTS {name} ON {table}'))
            clause=f'WITH CHECK ({expression})' if command=='INSERT' else f'USING ({expression})'
            if command=='UPDATE': clause+=f' WITH CHECK ({expression})'
            connection.execute(text(f'CREATE POLICY {name} ON {table} FOR {command} TO skelivia_worker {clause}'))
    connection.execute(text('DROP POLICY IF EXISTS worker_select ON domain_records'))
    connection.execute(text("CREATE POLICY worker_select ON domain_records FOR SELECT TO skelivia_worker USING (kind IN ('device','ticket','patch','incident','audit','settings'))"))
    connection.execute(text('DROP POLICY IF EXISTS worker_notify ON domain_records'))
    connection.execute(text("CREATE POLICY worker_notify ON domain_records FOR INSERT TO skelivia_worker WITH CHECK (kind IN ('notification','incident'))"))
    connection.execute(text('DROP POLICY IF EXISTS worker_read ON domain_diagnostics'))
    connection.execute(text('CREATE POLICY worker_read ON domain_diagnostics FOR SELECT TO skelivia_worker USING (true)'))
    connection.execute(text('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC'))
    connection.execute(text('REVOKE CREATE ON SCHEMA public FROM PUBLIC'))
    connection.execute(text('GRANT USAGE ON SCHEMA public TO skelivia_app,skelivia_worker'))
    connection.execute(text('GRANT SELECT,INSERT,UPDATE,DELETE ON accounts,web_sessions,login_limits,login_devices,oidc_states,logout_replays TO skelivia_app'))
    connection.execute(text('GRANT SELECT ON oidc_identities,care_links,support_scopes TO skelivia_app'))
    connection.execute(text('GRANT SELECT,INSERT ON audit TO skelivia_app'))
    connection.execute(text('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO skelivia_app'))
    connection.execute(text('GRANT SELECT,INSERT,UPDATE ON domain_records,domain_grants,domain_jobs,domain_diagnostics TO skelivia_app'))
    connection.execute(text('GRANT SELECT ON reports TO skelivia_app'))
    connection.execute(text('GRANT SELECT,UPDATE ON domain_records TO skelivia_worker'))
    connection.execute(text('GRANT INSERT ON domain_records TO skelivia_worker'))
    connection.execute(text('GRANT SELECT,UPDATE ON domain_jobs TO skelivia_worker'))
    connection.execute(text('GRANT SELECT ON domain_diagnostics,support_scopes TO skelivia_worker'))
    connection.execute(text('GRANT SELECT (id,active,role,org_id) ON accounts TO skelivia_worker'))
    connection.execute(text('GRANT SELECT (at,event) ON audit TO skelivia_worker'))
    connection.execute(text('GRANT SELECT ON service_heartbeats TO skelivia_app'))
    connection.execute(text('GRANT SELECT,INSERT,UPDATE ON service_heartbeats TO skelivia_worker'))
    connection.execute(text('DROP POLICY IF EXISTS worker_heartbeat ON service_heartbeats'))
    connection.execute(text("CREATE POLICY worker_heartbeat ON service_heartbeats TO skelivia_worker USING (id='ingestion') WITH CHECK (id='ingestion')"))
    for table in ('push_subscriptions','push_deliveries','push_schedules'):
        connection.execute(text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
        connection.execute(text(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY'))
        connection.execute(text(f'DROP POLICY IF EXISTS push_owner ON {table}'))
        connection.execute(text(f'CREATE POLICY push_owner ON {table} TO skelivia_push USING (owner_id={actor}) WITH CHECK (owner_id={actor})'))
        connection.execute(text(f'DROP POLICY IF EXISTS schema_owner ON {table}'))
        connection.execute(text(f'CREATE POLICY schema_owner ON {table} TO skelivia_owner USING (true) WITH CHECK (true)'))
    connection.execute(text('GRANT USAGE ON SCHEMA public TO skelivia_push'))
    connection.execute(text('GRANT SELECT,INSERT,UPDATE ON push_subscriptions TO skelivia_app'))
    connection.execute(text('GRANT SELECT ON push_deliveries TO skelivia_app'))
    connection.execute(text('GRANT SELECT,INSERT,UPDATE ON push_subscriptions,push_deliveries,push_schedules TO skelivia_push'))
    connection.execute(text('GRANT SELECT (id,active,role,org_id,patient_id) ON accounts TO skelivia_push'))
    connection.execute(text('GRANT SELECT,INSERT ON domain_records TO skelivia_push'))
    connection.execute(text('DROP POLICY IF EXISTS push_read ON domain_records'))
    connection.execute(text(f"CREATE POLICY push_read ON domain_records FOR SELECT TO skelivia_push USING (owner_id={actor} AND kind IN ('notification','settings'))"))
    connection.execute(text('DROP POLICY IF EXISTS push_insert ON domain_records'))
    connection.execute(text(f"CREATE POLICY push_insert ON domain_records FOR INSERT TO skelivia_push WITH CHECK (owner_id={actor} AND kind='notification')"))
    connection.execute(text('GRANT INSERT ON reports TO skelivia_worker'))
    connection.execute(text('GRANT SELECT ON transport_device_identity TO skelivia_worker'))
    connection.execute(text('GRANT SELECT,INSERT,UPDATE ON transport_ingest_cursor TO skelivia_worker'))
    connection.execute(text('GRANT SELECT,INSERT,UPDATE ON transport_device_cursor TO skelivia_worker'))
    connection.execute(text('GRANT SELECT,INSERT ON transport_ingest_receipt TO skelivia_worker'))


def main():
    register_models()
    engine=create_engine(runtime_url(),hide_parameters=True)
    if engine.dialect.name=='postgresql':
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE IF EXISTS transport_device_identity ADD COLUMN IF NOT EXISTS expires_at double precision'))
    Base.metadata.create_all(engine)
    if engine.dialect.name=='postgresql':
        with engine.begin() as conn:
            conn.execute(text('INSERT INTO transport_device_cursor(device_id,last_window_end) SELECT device_id,MAX(measured_at) FROM transport_ingest_receipt GROUP BY device_id ON CONFLICT (device_id) DO NOTHING'))
    factory=sessionmaker(engine,expire_on_commit=False)
    seed(factory)
    with factory() as db:
        seed_domain(db)
        mapping=os.getenv('SKELIVIA_OIDC_IDENTITY_MAP_FILE')
        if mapping:
            for subject,ident in json.loads(Path(mapping).read_text()).items():
                if not db.get(Account,ident): continue
                found=db.get(OIDCIdentity,subject)
                if found and found.user_id!=ident: raise RuntimeError('Identity mapping conflict.')
                if not found: db.add(OIDCIdentity(subject=subject,user_id=ident))
        registry=os.getenv('SKELIVIA_DEVICE_REGISTRY_FILE')
        if registry:
            from .transport_models import DeviceIdentity
            from .domain_models import DomainRecord
            for item in json.loads(Path(registry).read_text()):
                identity=db.get(DeviceIdentity,item['cert_cn'])
                if not identity: db.add(DeviceIdentity(**item))
                elif identity.cert_serial==item['cert_serial']:
                    identity.expires_at=item.get('expires_at')
                    if item.get('revoked_at'):
                        identity.revoked_at=identity.revoked_at or item['revoked_at']
                else:
                    raise RuntimeError('Registry certificate changed: explicit rotation required.')
                device=db.get(DomainRecord,item['device_id'])
                if device:
                    data=dict(device.data)
                    data['certificate']={**data.get('certificate',{}),'serial':item['cert_serial']}
                    if item.get('revoked_at') or (identity and identity.revoked_at): data['certificate']['revoked']=True
                    if item.get('expires_at'): data['certificate']['expires']=item['expires_at']
                    device.data=data
        db.commit()
    if engine.dialect.name=='postgresql':
        with engine.begin() as conn:
            install_policies(conn)
            conn.execute(text('CREATE TABLE IF NOT EXISTS schema_revisions (version integer PRIMARY KEY, installed_at timestamptz NOT NULL DEFAULT now())'))
            conn.execute(text('INSERT INTO schema_revisions(version) VALUES (1) ON CONFLICT DO NOTHING'))
    engine.dispose()
    print('Schema, synthetic fixtures, explicit identity mapping and row policies initialized. No secrets printed.')


if __name__=='__main__':
    main()
