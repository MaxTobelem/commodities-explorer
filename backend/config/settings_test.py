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
PRESSE_LOOKBACK_DAYS = 36500
MINING_LOOKBACK_DAYS = 36500
# Presse & mining are off by default in tests (no live feeds); their tests set their own.
PRESSE_FEEDS: list[tuple[str, str]] = []
MINING_FEEDS: list[tuple[str, str]] = []
# No network translation in tests; the dedicated test flips it on with a fake.
MINING_TRANSLATE = False
