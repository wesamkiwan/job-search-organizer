from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from .models import Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "website", "is_enabled", "posting_count")
    list_filter = ("kind", "is_enabled")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Source]:
        queryset: QuerySet[Source] = super().get_queryset(request)
        return queryset.annotate(_posting_count=Count("postings"))

    @admin.display(description="postings", ordering="_posting_count")
    def posting_count(self, obj: Source) -> int:
        return obj._posting_count  # type: ignore[attr-defined, no-any-return]
