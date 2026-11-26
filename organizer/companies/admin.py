from collections.abc import Sequence
from typing import ClassVar

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from .models import Company, Contact


class ContactInline(admin.TabularInline):
    """Shows (and lets you add) a company's contacts right on the company page."""

    model = Contact
    fields = ("first_name", "last_name", "job_title", "kind", "email")
    extra = 0  # no empty rows by default; click "Add another Contact"
    show_change_link = True  # link to the contact's full edit page


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    # Columns of the list page ("changelist").
    list_display = (
        "name",
        "industry",
        "size",
        "headquarters",
        "rating",
        "is_recruiting_agency",
        "contact_count",
    )
    list_filter = ("is_recruiting_agency", "size", "rating")
    search_fields = ("name", "industry", "headquarters", "locations")
    # Admin-only JavaScript that fills the slug while you type the name.
    prepopulated_fields: ClassVar[dict[str, Sequence[str]]] = {"slug": ("name",)}
    readonly_fields = ("created_at", "updated_at")
    inlines = (ContactInline,)
    # fieldsets = sections of the edit form; "collapse" hides a section until clicked.
    fieldsets = (
        (None, {"fields": ("name", "slug", "is_recruiting_agency", "rating")}),
        ("Links", {"fields": ("website", "careers_url", "linkedin_url")}),
        ("Details", {"fields": ("industry", "size", "headquarters", "locations", "description")}),
        ("Notes", {"fields": ("notes",)}),
        ("Custom fields", {"fields": ("custom_data",), "classes": ("collapse",)}),
        ("History", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Company]:
        # annotate(): the database counts each company's contacts in the SAME query that
        # loads the companies, instead of one extra COUNT query per row.
        # (ModelAdmin isn't generic, so mypy needs the type spelled out here.)
        queryset: QuerySet[Company] = super().get_queryset(request)
        return queryset.annotate(_contact_count=Count("contacts"))

    @admin.display(description="contacts", ordering="_contact_count")
    def contact_count(self, obj: Company) -> int:
        return obj._contact_count  # type: ignore[attr-defined, no-any-return]


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "company", "kind", "job_title", "email", "last_contacted_at")
    list_filter = ("kind",)
    # company__name: follow the ForeignKey and search in the company's name too.
    search_fields = ("first_name", "last_name", "email", "job_title", "company__name")
    # Load each contact's company in the same query (SQL JOIN), for the "company" column.
    list_select_related = ("company",)
    # A search box instead of a dropdown with every company (uses CompanyAdmin.search_fields).
    autocomplete_fields = ("company",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("first_name", "last_name", "job_title", "company", "kind")}),
        ("Contact details", {"fields": ("email", "phone", "linkedin_url")}),
        ("Notes", {"fields": ("notes", "last_contacted_at")}),
        ("Custom fields", {"fields": ("custom_data",), "classes": ("collapse",)}),
        ("History", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="name", ordering="last_name")
    def full_name(self, obj: Contact) -> str:
        return obj.full_name
