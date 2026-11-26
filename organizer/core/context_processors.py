"""Context processors: functions whose returned dict is available in every template."""

from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django.utils.functional import SimpleLazyObject

from .models import UserSettings


def dev_tools(request: HttpRequest) -> dict[str, Any]:
    """Tell templates whether development-only tools (like the UI kit link) are shown."""
    return {"show_dev_tools": settings.DEBUG}


def user_settings(request: HttpRequest) -> dict[str, Any]:
    """Make the app settings available in every template as {{ user_settings }}.

    SimpleLazyObject: the database is only asked when a template actually USES
    user_settings (e.g. for the date format), not on every page load.
    """
    return {"user_settings": SimpleLazyObject(UserSettings.load)}
