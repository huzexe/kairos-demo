"""
Django settings for Kairos.

Kairos runs locally on the agency's own computer. Everything that belongs to
one installation (database, secret key, uploaded files) lives in a single
data folder, so backing up or moving Kairos means copying one folder.

Environment variables:
    KAIROS_DATA_DIR   where the data folder lives (default: ./data)
    KAIROS_DEBUG      "1" turns on Django's debug pages (development only)
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("KAIROS_DATA_DIR", BASE_DIR / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_secret_key() -> str:
    """Each installation gets its own random secret key, created on first run."""
    key_file = DATA_DIR / "secret_key"
    if key_file.exists():
        return key_file.read_text().strip()
    key = secrets.token_urlsafe(50)
    key_file.write_text(key)
    try:
        key_file.chmod(0o600)
    except OSError:  # Windows ignores Unix permissions
        pass
    return key


SECRET_KEY = _load_secret_key()
DEBUG = os.environ.get("KAIROS_DEBUG") == "1"

# Kairos is served only on this computer.
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.pipeline",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.FirstRunSetupMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    "apps.core.middleware.AgencyTimezoneMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "kairos.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.agency",
            ],
        },
    },
]

WSGI_APPLICATION = "kairos.wsgi.application"

# SQLite: WAL mode keeps reads fast while writing, and IMMEDIATE transactions
# avoid "database is locked" errors when two requests write at once.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "kairos.sqlite3",
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                "PRAGMA synchronous=NORMAL;"
            ),
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

# Stay signed in for two weeks on this computer.
SESSION_COOKIE_AGE = 60 * 60 * 24 * 14
SESSION_COOKIE_HTTPONLY = True

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # stored in UTC; shown in the agency's own time zone
USE_I18N = False
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = DATA_DIR / "staticfiles"
# Serve straight from the source folders so no "collectstatic" step is needed.
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True

MEDIA_URL = "media/"
MEDIA_ROOT = DATA_DIR / "media"
