"""
Django settings for the commodities-explorer backend.

Settings are environment-driven (12-factor): a local `.env` file is loaded in
development, and real environment variables take precedence in production.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env (development convenience; real env vars win in production).
load_dotenv(BASE_DIR / ".env")


def env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def env_bool(key: str, default: bool = False) -> bool:
    return env(key, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    raw = env(key, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Core -------------------------------------------------------------------

SECRET_KEY = env(
    "SECRET_KEY",
    "django-insecure-$-gh#2$c(h-&zsq1n5v2wt@a&wci6lk@6l7a^0u1jp&5-^rsax",
)

DEBUG = env_bool("DEBUG", True)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")


# --- Applications -----------------------------------------------------------

INSTALLED_APPS = [
    # django-unfold must come before django.contrib.admin.
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party.
    "rest_framework",
    "django_filters",
    # Local.
    "commodities",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database ---------------------------------------------------------------
# SQLite by default (dev/tests); set DATABASE_URL (postgres://...) in production.

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}


# --- Auth -------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalization ---------------------------------------------------

LANGUAGE_CODE = env("LANGUAGE_CODE", "fr-fr")
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# --- Static files -----------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Django REST Framework --------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}


# --- django-unfold (admin theme) --------------------------------------------

UNFOLD = {
    "SITE_TITLE": "Matières premières — Admin",
    "SITE_HEADER": "Matières premières",
    "SITE_SUBHEADER": "Console d'administration & d'import",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
}


# --- Email (passwordless login codes; configured fully in M4) ----------------

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",  # dev: prints to console
)
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "no-reply@commodities-explorer.local")


# --- Data sources -----------------------------------------------------------

# Commodities-API (prices). Set COMMODITIES_API_KEY in the environment / .env.
COMMODITIES_API_KEY = env("COMMODITIES_API_KEY", "")
COMMODITIES_API_BASE_URL = env("COMMODITIES_API_BASE_URL", "https://api.commodities-api.com/api")
COMMODITIES_API_TIMEOUT = int(env("COMMODITIES_API_TIMEOUT", "20"))
COMMODITIES_API_RATE_IS_PER_USD = env_bool("COMMODITIES_API_RATE_IS_PER_USD", True)
# Symbols-per-request cap (plan-dependent): PRO=10, PRO PLUS=15, ADVANCED=20…
# update_prices chunks requests accordingly (1 slot reserved for EUR conversion).
COMMODITIES_API_MAX_SYMBOLS = int(env("COMMODITIES_API_MAX_SYMBOLS", "10"))

# GDELT (events) — bulk daily Events export (no rate-limited API).
# Scan the last N daily files; flag a producing country once its material-conflict
# coverage over the window crosses GDELT_MIN_ARTICLES (tuned against real volume).
GDELT_EVENTS_URL = env("GDELT_EVENTS_URL", "http://data.gdeltproject.org/events")
GDELT_LOOKBACK_DAYS = int(env("GDELT_LOOKBACK_DAYS", "3"))
GDELT_MIN_ARTICLES = int(env("GDELT_MIN_ARTICLES", "3000"))
GDELT_TIMEOUT = int(env("GDELT_TIMEOUT", "30"))

# USGS (reserves/production) — bump USGS_MCS_ITEM_ID to the new ScienceBase item each year.
USGS_ENABLED = env_bool("USGS_ENABLED", True)
USGS_MCS_ITEM_ID = env("USGS_MCS_ITEM_ID", "677eaf95d34e760b392c4970")  # MCS 2025

# World Bank Pink Sheet (free monthly prices). EUR is an approximate conversion (prices are USD-only).
WORLD_BANK_XLSX_URL = env(
    "WORLD_BANK_XLSX_URL",
    "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/"
    "related/CMO-Historical-Data-Monthly.xlsx",
)
EUR_USD_RATE = env("EUR_USD_RATE", "0.92")

# Our World in Data (production by country: agriculture FAO + energy).
OWID_ENABLED = env_bool("OWID_ENABLED", True)


# --- Production hardening (only when DEBUG is off) ---------------------------

if not DEBUG:
    # Serve hashed, compressed static files (admin/unfold/DRF) via WhiteNoise.
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
