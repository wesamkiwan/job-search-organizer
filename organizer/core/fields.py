"""Custom model fields shared by all apps."""

from typing import Any

from django.db import models


class HttpsURLField(models.URLField):
    """A URLField that completes "stepstone.de" to "https://stepstone.de" (not "http://").

    Every model field knows which form field represents it in forms and the admin
    (formfield()). We only change one option of that form field. Django 6.0 makes https
    the default, so after upgrading this class can simply become models.URLField again.
    """

    def formfield(self, **kwargs: Any) -> Any:
        kwargs.setdefault("assume_scheme", "https")
        return super().formfield(**kwargs)
