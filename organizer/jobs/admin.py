from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from .models import JobPosting, Tag


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "posting_count")
    list_filter = ("color",)
    search_fields = ("name",)  # also needed for autocomplete_fields on JobPostingAdmin

    def get_queryset(self, request: HttpRequest) -> QuerySet[Tag]:
        queryset: QuerySet[Tag] = super().get_queryset(request)
        return queryset.annotate(_posting_count=Count("postings"))

    @admin.display(description="postings", ordering="_posting_count")
    def posting_count(self, obj: Tag) -> int:
        return obj._posting_count  # type: ignore[attr-defined, no-any-return]


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "company_display",
        "source",
        "city",
        "remote_type",
        "triage_status",
        "found_at",
    )
    list_filter = (
        "triage_status",
        "source",
        "remote_type",
        "employment_type",
        "contract_type",
        "seniority",
        "tags",
    )
    search_fields = ("title", "company__name", "company_name_raw", "city", "description_text")
    # Date links above the list: year → month → day.
    date_hierarchy = "found_at"
    # company and source are shown in every row: load them in the same query (JOIN).
    list_select_related = ("company", "source")
    autocomplete_fields = ("company", "tags")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("title", "company", "company_name_raw", "url", "source", "tags")}),
        ("Status", {"fields": ("triage_status", "found_at", "date_posted", "valid_through")}),
        (
            "Location",
            {
                "fields": (
                    "location_text",
                    "city",
                    "postal_code",
                    "country",
                    "remote_type",
                    "distance_km",
                )
            },
        ),
        (
            "Job",
            {"fields": ("employment_type", "contract_type", "seniority", "posting_language")},
        ),
        ("Salary", {"fields": ("salary_min", "salary_max", "salary_currency", "salary_period")}),
        ("Description", {"fields": ("description_text",)}),
        ("Custom fields", {"fields": ("custom_data",), "classes": ("collapse",)}),
        ("History", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="company", ordering="company__name")
    def company_display(self, obj: JobPosting) -> str:
        return obj.company_display
