"""Settings used when running the automated tests."""

from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "django-insecure-test-only"  # noqa: S105 (not a real secret)
ALLOWED_HOSTS = ["testserver"]

# A deliberately weak but very fast password hasher: makes tests that create users quicker.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
