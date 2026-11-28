from django.contrib import admin

from .models import Goal


@admin.register(Goal)
class GoalAdmin(admin.ModelAdmin):
    list_display = ("__str__", "metric", "target", "period", "is_active")
    list_editable = ("target", "is_active")
    list_filter = ("is_active", "period")
    readonly_fields = ("created_at", "updated_at")
