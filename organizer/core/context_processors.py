"""Context processors: functions whose returned dict is available in every template."""

from typing import Any

from django.conf import settings
from django.http import HttpRequest


def dev_tools(request: HttpRequest) -> dict[str, Any]:
    """Tell templates whether development-only tools (like the UI kit link) are shown."""
    return {"show_dev_tools": settings.DEBUG}
