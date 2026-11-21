"""ASGI entry point: like wsgi.py, for asynchronous servers (e.g. uvicorn)."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

application = get_asgi_application()
