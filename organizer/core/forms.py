"""Forms for the core app."""

from django import forms

from .models import UserSettings


class UserSettingsForm(forms.ModelForm):
    """Edit the app settings. Labels, help texts, choices and validation come from the model."""

    class Meta:
        model = UserSettings
        fields = ("home_location", "default_currency", "ghosted_after_days", "date_format")
