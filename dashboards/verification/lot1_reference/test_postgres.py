import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError


def test_postgres_application_has_no_administrative_or_ddl_rights(database_url):
    engine=create_engine(database_url,hide_parameters=True)
    try:
        if engine.dialect.name!='postgresql':
            pytest.skip('PostgreSQL integration test; run with --postgres')
        with engine.connect() as conn:
            role=conn.exec_driver_sql('SELECT current_user,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls FROM pg_roles WHERE rolname=current_user').one()
            assert role[0]=='p2_app' and not any(role[1:])
            assert not conn.exec_driver_sql("SELECT has_database_privilege(current_user,current_database(),'CREATE') OR has_database_privilege(current_user,current_database(),'TEMP')").scalar()
            conn.rollback()
            for command in ['CREATE TABLE forbidden(id integer)','ALTER TABLE accounts ADD COLUMN forbidden integer','DROP TABLE accounts','TRUNCATE accounts']:
                with pytest.raises(ProgrammingError) as failure:
                    conn.exec_driver_sql(command)
                assert failure.value.orig.sqlstate=='42501'
                conn.rollback()
    finally:
        engine.dispose()
