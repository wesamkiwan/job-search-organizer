from typing import Any

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest

from .models import ApplicationDocument, Document, DocumentType, DocumentVersion


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "order", "document_count")
    list_editable = ("order",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[DocumentType]:
        queryset: QuerySet[DocumentType] = super().get_queryset(request)
        return queryset.annotate(_document_count=Count("documents"))

    @admin.display(description="documents", ordering="_document_count")
    def document_count(self, obj: DocumentType) -> int:
        return obj._document_count  # type: ignore[attr-defined, no-any-return]


class VersionInline(admin.TabularInline):
    """The document's versions, read-only here: files are added through the services."""

    model = DocumentVersion
    fields = ("version_number", "original_filename", "size_bytes", "created_at", "change_notes")
    readonly_fields = fields
    extra = 0
    show_change_link = True  # a link to the version's own admin page

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "document_type", "language", "version_count", "is_archived")
    list_filter = ("document_type", "language", "is_archived", "tags")
    search_fields = ("title", "description")
    list_select_related = ("document_type",)
    autocomplete_fields = ("tags",)
    inlines = (VersionInline,)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[Document]:
        queryset: QuerySet[Document] = super().get_queryset(request)
        return queryset.annotate(_version_count=Count("versions"))

    @admin.display(description="versions", ordering="_version_count")
    def version_count(self, obj: Document) -> int:
        return obj._version_count  # type: ignore[attr-defined, no-any-return]


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "original_filename", "mime_type", "size_bytes", "created_at")
    list_filter = ("mime_type", "document__document_type")
    search_fields = ("document__title", "original_filename", "change_notes")
    list_select_related = ("document",)
    # Everything except the notes is fixed once the file is uploaded.
    readonly_fields = (
        "document",
        "version_number",
        "file",
        "original_filename",
        "mime_type",
        "size_bytes",
        "sha256",
        "extracted_text",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # uploads go through the services (step 2.2)


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = ("document_version", "application", "sent_at")
    search_fields = ("document_version__document__title", "application__posting__title")
    list_select_related = ("document_version__document", "application__posting")
    autocomplete_fields = ("application", "document_version")
    readonly_fields = ("created_at", "updated_at")
