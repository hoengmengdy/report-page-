from pathlib import Path
from cryptography.fernet import Fernet
from sqlalchemy import inspect, text
from backend import create_app
from backend.models import db


def test_fresh_sqlite_database_is_migrated_and_restart_is_idempotent(tmp_path):
    url = 'sqlite:///' + (Path(tmp_path) / 'fresh.db').as_posix()
    config = {"DEMO_MODE":"true", "SECRET_KEY":"test-secret-key-at-least-thirty-two-characters",
              "TOKEN_ENCRYPTION_KEY":Fernet.generate_key().decode(), "SQLALCHEMY_DATABASE_URI":url}
    for _ in range(2):
        app = create_app(config)
        with app.app_context():
            assert 'browser_sessions' in inspect(db.engine).get_table_names()
            assert db.session.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0001'
            db.session.remove()
            db.engine.dispose()
