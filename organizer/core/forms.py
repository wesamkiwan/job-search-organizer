"""Forms for the core app, and form widgets shared by all apps."""

from typing import Any

from django import forms
from django.contrib import messages
from django.http import HttpRequest
from django.utils import timezone

from .models import UserSettings


class UserSettingsForm(forms.ModelForm):
    """Edit the app settings. Labels, help texts, choices and validation come from the model."""

    class Meta:
        model = UserSettings
        fields = ("home_location", "default_currency", "ghosted_after_days", "date_format")


# --- Widgets ---------------------------------------------------------------------------
# Django's DateInput renders <input type="text">. With type="date" the browser shows its
# own date picker. The value must then be in ISO format (2026-11-27), whatever the
# display format in Settings is; the browser shows it in the user's local style.


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(format="%Y-%m-%d", **kwargs)


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"  # date + time picker, e.g. 2026-11-27T14:05

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


def now_for_input() -> str:
    """The current local time in the format a datetime-local input expects."""
    return timezone.localtime().strftime("%Y-%m-%dT%H:%M")


def form_errors_to_messages(request: HttpRequest, form: forms.BaseForm) -> None:
    """Show a small action form's errors as messages (the form lives in a card or dialog,
    and the view redirects back to the page instead of showing the form again)."""
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else ""
        for error in errors:
            messages.error(request, f"{label}: {error}" if label else str(error))
