"""Production entry point: migrate the database and run one Waitress process."""
import os

from flask_migrate import upgrade
from waitress import serve

from . import ROOT, create_app


def main():
    app = create_app()
    # SQLite is migrated by create_app; hosted PostgreSQL needs the same schema.
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:"):
        with app.app_context():
            upgrade(directory=str(ROOT / "migrations"))
    serve(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")), threads=8)


if __name__ == "__main__":
    main()
