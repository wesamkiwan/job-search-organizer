"""Settings for local development on your own machine."""

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# A fixed key is acceptable locally only. Production requires a real secret (see production.py).
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-local-development-only")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
