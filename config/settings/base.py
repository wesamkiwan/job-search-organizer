"""Settings shared by every environment (local, test, production).

Environment-specific files (local.py, test.py, production.py) import everything from
here and then override what differs. Values that change between machines or contain
secrets are read from environment variables / the .env file, never hard-coded.
"""

from pathlib import Path

import environ
from django.contrib.messages import constants as messages

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
THIRD_PARTY_APPS = [
    # SimpleAppConfig: cotton does NOT rewrite TEMPLATES behind our back;
    # its loader and tags are configured explicitly in TEMPLATES below.
    "django_cotton.apps.SimpleAppConfig",
    "django_tailwind_cli",
]
LOCAL_APPS = [
    "organizer.core",
    "organizer.accounts",
    "organizer.companies",
    "organizer.sources",
    "organizer.jobs",
    "organizer.applications",
    "organizer.documents",
    "organizer.analytics",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# --- Request handling ---------------------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Every page requires login unless its view is marked @login_not_required
    # ("secure by default": a new page can't be public by accident). Needs Django 5.1+.
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
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
        # No APP_DIRS: it can't be combined with an explicit "loaders" list. The
        # app_directories loader below does the same job (finds app/templates/ folders).
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "organizer.core.context_processors.dev_tools",
                "organizer.core.context_processors.user_settings",
                "organizer.core.context_processors.current_time",
            ],
            # Loaders are tried in order. The cotton loader first compiles <c-...> component
            # tags into normal Django template tags. The cached loader keeps compiled
            # templates in memory (in development it reloads them when a file changes).
            "loaders": [
                (
                    "django.template.loaders.cached.Loader",
                    [
                        "django_cotton.cotton_loader.Loader",
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                    ],
                ),
            ],
            # Built-ins are available in every template without {% load %}.
            "builtins": ["django_cotton.templatetags.cotton"],
        },
    },
]

# --- Components (django-cotton) -----------------------------------------------------
# <c-button> renders templates/components/button.html.
COTTON_DIR = "components"
# Components only see the attributes passed to them (plus request/user from context
# processors), not every variable of the page that uses them. Like function arguments:
# explicit inputs, no hidden dependencies.
COTTON_ISOLATE_BY_DEFAULT = True


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

# Our own user model (organizer/accounts/models.py) instead of django.contrib.auth's.
# Must be set before the first migration; code refers to it via get_user_model() or
# settings.AUTH_USER_MODEL, never by importing django.contrib.auth.models.User.
AUTH_USER_MODEL = "accounts.User"

# Where to send people: URL names, resolved by Django like {% url %}.
LOGIN_URL = "accounts:login"  # not logged in -> here (with ?next=<page they wanted>)
LOGIN_REDIRECT_URL = "core:home"  # after logging in, if there is no ?next=
LOGOUT_REDIRECT_URL = "accounts:login"  # after logging out

# Messages framework: Django's "error" level is called "danger" in our alert component.
MESSAGE_TAGS = {messages.ERROR: "danger"}

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

# Our own setting (any UPPERCASE name in a settings file works): the largest document
# file that can be uploaded, in bytes. Read with django.conf.settings.DOCUMENT_MAX_UPLOAD_SIZE.
DOCUMENT_MAX_UPLOAD_SIZE = env.int("DOCUMENT_MAX_UPLOAD_SIZE", default=10 * 1024 * 1024)  # 10 MB


# --- Tailwind CSS (django-tailwind-cli) ---------------------------------------------
# The standalone Tailwind binary (no Node.js needed) scans our templates for class
# names and compiles SRC_CSS into DIST_CSS. DIST_CSS is relative to STATICFILES_DIRS[0]
# and is a build output, so it is git-ignored.

TAILWIND_CLI_VERSION = "4.3.5"  # pinned: "latest" would change the build silently
TAILWIND_CLI_SRC_CSS = "assets/css/source.css"
TAILWIND_CLI_DIST_CSS = "css/dist/tailwind.css"
