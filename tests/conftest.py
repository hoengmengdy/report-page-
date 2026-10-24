import secrets
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from backend import create_app
from backend.models import BrowserSession, db


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "DEMO_MODE": "true", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                      "SECRET_KEY": "test-secret-key-of-at-least-thirty-two-characters", "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode()})
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def live_app():
    app = create_app({"TESTING": True, "DEMO_MODE": "false", "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
                      "SECRET_KEY": "test-secret-key-of-at-least-thirty-two-characters", "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
                      "META_APP_ID": "1234", "META_APP_SECRET": "test-app-secret"})
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(live_app):
    client = live_app.test_client()
    client.get("/api/session")
    sid = secrets.token_urlsafe(32)
    with live_app.app_context():
        record = BrowserSession(id=sid, meta_user_id="123456", expires_at=datetime.now(timezone.utc)+timedelta(hours=8))
        record.write({"user_token": "SECRET_USER_TOKEN", "permissions": ["read_insights"],
                      "selected_page": {"id": "67890", "name": "Real Test Page", "link": "https://www.facebook.com/TestPage",
                                        "access_token": "SECRET_PAGE_TOKEN", "tasks": ["ANALYZE"]}})
        db.session.add(record)
        db.session.commit()
    with client.session_transaction() as state:
        state["sid"] = sid
    return client


def csrf(client):
    return {"X-CSRF-Token": client.get("/api/session").json["csrf_token"]}
