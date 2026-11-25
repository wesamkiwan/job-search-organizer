from django.contrib import admin
from django.http import HttpRequest

from .models import UserSettings


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    """The single settings row: it can be edited, but not added twice or deleted."""

    readonly_fields = ("updated_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not UserSettings.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: UserSettings | None = None) -> bool:
        return False
