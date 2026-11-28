from django.contrib import admin

from .models import DashboardLayout, Goal


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("__str__", "metric", "target", "period", "is_active")
    list_editable = ("target", "is_active")
    list_filter = ("is_active", "period")
    readonly_fields = ("created_at", "updated_at")


@admin.register(DashboardLayout)
class DashboardLayoutAdmin(admin.ModelAdmin):
    """For looking at (or repairing) the saved layout. The dashboard's "Customize" mode is
    the normal way to change it; analytics/layout.py ignores anything invalid here."""

    list_display = ("name", "updated_at")
    readonly_fields = ("created_at", "updated_at")
