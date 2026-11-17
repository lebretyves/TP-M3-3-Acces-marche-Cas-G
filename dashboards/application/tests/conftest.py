"""Tests use isolated SQLite banks; live PostgreSQL probes run app.verify_domain_pg."""
import pytest

@pytest.fixture
def database_url(tmp_path):
    return 'sqlite:///'+(tmp_path/'test.db').as_posix()
