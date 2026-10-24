"""Server-side sessions; the browser never receives Meta tokens."""
import json
from datetime import datetime, timezone
from flask import current_app
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class BrowserSession(db.Model):
    __tablename__ = "browser_sessions"
    id = db.Column(db.String(64), primary_key=True)
    meta_user_id = db.Column(db.String(64), index=True, nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    encrypted_payload = db.Column(db.Text, nullable=False)

    def read(self):
        return json.loads(current_app.extensions["token_cipher"].decrypt(
            self.encrypted_payload.encode()).decode())

    def write(self, payload):
        self.encrypted_payload = current_app.extensions["token_cipher"].encrypt(
            json.dumps(payload).encode()).decode()

    @property
    def expired(self):
        return self.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc)
