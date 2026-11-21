"""Settings shared by every environment (local, test, production).

Environment-specific files (local.py, test.py, production.py) import everything from
here and then override what differs. Values that change between machines or contain
secrets are read from environment variables / the .env file, never hard-coded.
"""

from pathlib import Path

import environ

# Project root: the folder that contains manage.py
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Load variables from .env if the file exists (local development).
# In production, real environment variables are used instead.
environ.Env.read_env(BASE_DIR / ".env")


# --- Applications -------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]
THIRD_PARTY_APPS: list[str] = []
LOCAL_APPS: list[str] = []

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# --- Request handling ---------------------------------------------------------------

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
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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
            ],
        },
    },
]


# --- Database -----------------------------------------------------------------------
# DATABASE_URL selects the database, e.g. "postgres://user:pass@host:5432/name".
# Without it, a local SQLite file is used.

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}",
    ),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --- Authentication -----------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Internationalization -----------------------------------------------------------
# English UI; "en-gb" gives day-month date formats, which are familiar in Germany.

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True


# --- Static files (CSS, JavaScript, images) and uploaded media ----------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"  # where "collectstatic" gathers files for production

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"  # uploaded documents (never committed to git)
