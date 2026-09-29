"""Settings, read from the environment once at import.

A .env file at the repo root is loaded first, so local runs pick up
SECRET_KEY / ADMIN_USER / ADMIN_PASSWORD without exporting anything.
Real environment variables always win over .env.
"""

import os

from dotenv import load_dotenv

load_dotenv()          # no-op when .env is absent, as in production


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")
    # None means "instance/tracker.db"; create_app() fills it in, since only
    # the app knows its own instance path.
    DB_PATH = os.environ.get("TRACKER_DB")


class TestConfig(Config):
    TESTING = True
    SECRET_KEY = "test"
    ADMIN_USER = "admin"
    ADMIN_PASSWORD = "test-pw"
    # DB_PATH is injected per-test by the conftest fixture.
