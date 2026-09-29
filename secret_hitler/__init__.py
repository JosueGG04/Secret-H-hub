"""Secret Hitler — Table Records.

A Flask + htmx tracker for Secret Hitler game night results.

Run:
    pip install -r requirements.txt
    python -m flask --app wsgi run --debug
Then open http://127.0.0.1:5000

The SQLite database (instance/tracker.db) is created on first run.
"""

import os

from flask import Flask

from . import db
from .auth import inject_admin
from .config import Config


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config or Config)

    os.makedirs(app.instance_path, exist_ok=True)
    if not app.config.get("DB_PATH"):
        app.config["DB_PATH"] = os.path.join(app.instance_path, "tracker.db")

    db.init_app(app)
    app.context_processor(inject_admin)

    # Registered late so the view modules can import from this package's
    # siblings without importing the factory back.
    from .auth import bp as auth_bp
    from .views.admin import bp as admin_bp
    from .views.public import bp as public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(auth_bp)

    # The schema is all CREATE TABLE IF NOT EXISTS, so this is cheap and
    # idempotent — it keeps the "just run it" setup the README promises,
    # without the import-time side effect the old app.py had.
    with app.app_context():
        db.init_db()

    return app
