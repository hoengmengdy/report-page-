from unittest.mock import Mock

import pytest

from backend import database_uri
from backend import serve as production


@pytest.mark.parametrize('prefix', ['postgres://', 'postgresql://'])
def test_provider_database_urls_use_the_installed_psycopg_driver(prefix):
    assert database_uri(prefix + 'user:p%40ss@db.example.com/app?sslmode=require') == (
        'postgresql+psycopg://user:p%40ss@db.example.com/app?sslmode=require')


def test_local_sqlite_and_explicit_driver_urls_remain_usable():
    for uri in ['sqlite:///pagepulse.db', 'postgresql+psycopg://user@db/app']:
        assert database_uri(uri) == uri


@pytest.mark.parametrize('database,needs_migration', [
    ('sqlite:///:memory:', False), ('postgresql+psycopg://user@db/app', True),
])
def test_production_startup_migrates_postgres_before_serving_on_the_host_port(app, monkeypatch, database, needs_migration):
    monkeypatch.setitem(app.config, 'SQLALCHEMY_DATABASE_URI', database)
    monkeypatch.setattr(production, 'create_app', lambda: app)
    monkeypatch.setenv('PORT', '9123')
    calls = Mock()
    monkeypatch.setattr(production, 'upgrade', calls.upgrade)
    monkeypatch.setattr(production, 'serve', calls.serve)
    production.main()
    assert calls.upgrade.called is needs_migration
    calls.serve.assert_called_once_with(app, host='0.0.0.0', port=9123, threads=8)
    if needs_migration:
        assert [call[0] for call in calls.mock_calls] == ['upgrade', 'serve']
