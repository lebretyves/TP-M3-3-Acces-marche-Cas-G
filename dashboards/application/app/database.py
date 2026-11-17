from pathlib import Path
import os
from sqlalchemy import create_engine, text, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

ROOT = Path(__file__).resolve().parents[1]


def runtime_url():
    filename = os.getenv('SKELIVIA_DATABASE_URL_FILE')
    value = Path(filename).read_text(encoding='utf-8').strip() if filename else os.getenv('P2_DATABASE_URL')
    if value:
        return make_url(value)
    if os.getenv('SKELIVIA_AUTH_MODE', 'local') != 'local':
        raise RuntimeError('Explicit PostgreSQL connection required in OIDC mode.')
    return make_url(f"sqlite:///{(ROOT/'.runtime/skelivia.db').as_posix()}")


def register_models():
    from . import domain_models
    from . import push_models
    from . import security_monitor
    try:
        from . import transport_models
    except ModuleNotFoundError as error:
        if error.name != 'app.transport_models':
            raise


def database(url=None):
    register_models()
    url = make_url(url or runtime_url())
    if url.drivername not in ('sqlite', 'postgresql+psycopg'):
        raise RuntimeError('Unsupported database driver.')
    if os.getenv('SKELIVIA_AUTH_MODE', 'local') == 'oidc' and url.drivername == 'sqlite':
        raise RuntimeError('OIDC service requires PostgreSQL.')
    args = {'check_same_thread':False} if url.drivername=='sqlite' else {'connect_timeout':5}
    engine = create_engine(url, connect_args=args, pool_pre_ping=True, hide_parameters=True)
    if url.drivername == 'sqlite':
        (ROOT/'.runtime').mkdir(exist_ok=True)
        @event.listens_for(engine, 'connect')
        def pragmas(connection, record):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=5000')
        Base.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def configure_actor(db, actor):
    """Install a transaction-local RLS context from a verified server identity."""
    if db.bind.dialect.name != 'postgresql':
        return
    values = {'skelivia.actor':actor.id, 'skelivia.role':actor.role,
              'skelivia.patient':actor.patient_id or '', 'skelivia.org':actor.org_id}
    db.info['skelivia_actor'] = values
    for name, value in values.items():
        db.execute(text('SELECT set_config(:name, :value, true)'), {'name':name, 'value':value})


@event.listens_for(Session, 'after_begin')
def restore_transaction_context(session, transaction, connection):
    if connection.dialect.name == 'postgresql':
        for name,value in session.info.get('skelivia_actor',{}).items():
            connection.execute(text('SELECT set_config(:name, :value, true)'), {'name':name,'value':value})
