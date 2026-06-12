"""Test settings: same as base, but an in-memory SQLite DB.

Used only by pytest (see pyproject.toml). Keeps the suite fast and independent
of Docker/Postgres, regardless of what DATABASE_URL the local .env points to.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Deterministic GDELT tests: scan a single day, low article threshold.
GDELT_LOOKBACK_DAYS = 1
GDELT_MIN_ARTICLES = 50
