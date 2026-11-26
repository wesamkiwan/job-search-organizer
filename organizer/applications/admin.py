from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

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
    model = ApplicationEvent
    fields = ("occurred_at", "kind", "from_stage", "to_stage", "summary")
    extra = 0


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
    readonly_fields = ("created_at", "updated_at")
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


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "application", "due_on", "done_at")
    list_filter = ("due_on", "done_at")
    search_fields = ("title", "notes", "application__posting__title")
    list_select_related = ("application__posting",)
    autocomplete_fields = ("application",)
    readonly_fields = ("created_at", "updated_at")
