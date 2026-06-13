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

# News tests: wide lookback so fixed-date fixture articles always pass the cutoff.
GNEWS_LOOKBACK_DAYS = 36500
