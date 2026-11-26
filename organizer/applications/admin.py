from typing import Any

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.forms import ModelForm
from django.http import HttpRequest

from . import services
from .models import Application, ApplicationEvent, PipelineStage, Task


@admin.register(PipelineStage)
class PipelineStageAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "category", "color", "is_default_for_category", "app_count")
    # list_editable: change these columns directly in the list, then "Save".
    list_editable = ("order", "color")
    list_filter = ("category",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[PipelineStage]:
        queryset: QuerySet[PipelineStage] = super().get_queryset(request)
        return queryset.annotate(_app_count=Count("applications"))

    @admin.display(description="applications", ordering="_app_count")
    def app_count(self, obj: PipelineStage) -> int:
        return obj._app_count  # type: ignore[attr-defined, no-any-return]


class EventInline(admin.TabularInline):
    """The timeline, read-only: events are written by the services, never by hand here."""

    model = ApplicationEvent
    fields = ("occurred_at", "kind", "from_stage", "to_stage", "summary")
    readonly_fields = fields
    extra = 0

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class TaskInline(admin.TabularInline):
    model = Task
    fields = ("title", "due_on", "done_at")
    extra = 0


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "posting",
        "company",
        "stage",
        "applied_on",
        "priority",
        "interest",
        "closed_at",
    )
    list_filter = ("stage", "channel", "priority", "is_archived", "tags")
    search_fields = ("posting__title", "posting__company__name", "posting__company_name_raw")
    # Two levels deep: application → posting → company, all in one query.
    list_select_related = ("posting__company", "stage")
    autocomplete_fields = ("posting", "referred_by", "tags")
    inlines = (EventInline, TaskInline)
    fieldsets = (
        (None, {"fields": ("posting", "stage", "applied_on", "channel", "referred_by", "tags")}),
        ("Your view", {"fields": ("priority", "interest", "follow_up_on", "notes")}),
        (
            "Conditions",
            {
                "fields": (
                    "salary_expectation",
                    "salary_expectation_currency",
                    "earliest_start_date",
                    "notice_period",
                )
            },
        ),
        (
            "Outcome",
            {
                "fields": (
                    "closed_at",
                    "outcome_stage",
                    "rejection_reason",
                    "rejection_details",
                    "is_archived",
                )
            },
        ),
        ("Custom fields", {"fields": ("custom_data",), "classes": ("collapse",)}),
        ("History", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="company", ordering="posting__company__name")
    def company(self, obj: Application) -> str:
        return obj.posting.company_display

    # The stage and the outcome fields belong to the services (see services.py). On an
    # existing application they are read-only here; stage changes come with the app's own
    # pages (step 1.7). When ADDING, you pick the starting stage.
    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> list[str]:
        fields = ["created_at", "updated_at", "closed_at", "outcome_stage"]
        if obj is not None:
            fields.append("stage")
        return fields

    def save_model(
        self, request: HttpRequest, obj: Application, form: ModelForm, change: bool
    ) -> None:
        if change:
            super().save_model(request, obj, form, change)
        else:
            # A new application goes through the service, so it gets its first event.
            services.create_application(obj)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "application", "due_on", "done_at")
    list_filter = ("due_on", "done_at")
    search_fields = ("title", "notes", "application__posting__title")
    list_select_related = ("application__posting",)
    autocomplete_fields = ("application",)
    readonly_fields = ("created_at", "updated_at")
