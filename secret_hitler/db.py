"""SQLite access: one connection per request, parked on flask.g."""

import sqlite3
from importlib import resources

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def schema_sql():
    """Read schema.sql as a package resource, so it survives being installed."""
    return resources.files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")


def init_db():
    """Create any missing tables. Idempotent — the schema is all IF NOT EXISTS."""
    db = sqlite3.connect(current_app.config["DB_PATH"])
    try:
        db.executescript(schema_sql())
        db.commit()
    finally:
        db.close()


@click.command("init-db")
def init_db_command():
    """Create the database tables if they don't exist yet."""
    init_db()
    click.echo("Initialised %s" % current_app.config["DB_PATH"])


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
