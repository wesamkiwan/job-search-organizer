from datetime import datetime
from typing import Any

from django import forms
from django.contrib import admin
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Count, QuerySet
from django.http import HttpRequest
from django.utils import timezone

from . import services
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

    # Through the service, so the files are deleted from the disk too.
    def delete_model(self, request: HttpRequest, obj: Document) -> None:
        services.delete_document(obj)

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[Document]) -> None:
        for document in queryset:
            services.delete_document(document)


class UploadVersionForm(forms.ModelForm):
    """The admin's "add version" form: the file is checked in clean(), so a problem (wrong
    type, too large, duplicate) is shown next to the field instead of crashing."""

    class Meta:
        model = DocumentVersion
        fields = ("document", "file", "change_notes")

    def clean_file(self) -> UploadedFile:
        file: UploadedFile = self.cleaned_data["file"]
        try:
            services.check_upload(file)
        except services.DocumentError as error:
            raise forms.ValidationError(str(error)) from error
        return file


# Fields that are fixed once the file is uploaded (only the notes can change).
VERSION_READONLY_FIELDS = (
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


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "original_filename", "mime_type", "size_bytes", "created_at")
    list_filter = ("mime_type", "document__document_type")
    search_fields = ("document__title", "original_filename", "change_notes")
    list_select_related = ("document",)
    autocomplete_fields = ("document",)

    # Adding: the small upload form. Changing: everything read-only except the notes.
    # (The return type is in quotes: ModelForm[Any] only exists for mypy, not at runtime.)
    def get_form(
        self, request: HttpRequest, obj: Any = None, change: bool = False, **kwargs: Any
    ) -> "type[forms.ModelForm[Any]]":
        if obj is None:
            kwargs["form"] = UploadVersionForm
        return super().get_form(request, obj, change, **kwargs)

    def get_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return UploadVersionForm.Meta.fields
        return (*VERSION_READONLY_FIELDS, "change_notes")

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        return () if obj is None else VERSION_READONLY_FIELDS

    def save_model(
        self, request: HttpRequest, obj: DocumentVersion, form: forms.ModelForm, change: bool
    ) -> None:
        if change:
            super().save_model(request, obj, form, change)
        else:
            # The new version goes through the service. The admin then needs obj to be the
            # saved row (it builds the "added" message and the redirect from it), so point
            # obj at the new row and reload all its fields from the database.
            saved = services.upload_version(
                obj.document,
                form.cleaned_data["file"],
                change_notes=form.cleaned_data["change_notes"],
            )
            obj.pk = saved.pk
            obj.refresh_from_db()

    def save_related(
        self, request: HttpRequest, form: forms.ModelForm, formsets: Any, change: bool
    ) -> None:
        if change:
            super().save_related(request, form, formsets, change)
        # When adding there is nothing related to save, and form.save_m2m() would try to
        # use the unsaved form instance.

    # A sent version can't be deleted (the delete button disappears).
    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        if obj is not None and obj.is_sent:
            return False
        return super().has_delete_permission(request, obj)

    def delete_model(self, request: HttpRequest, obj: DocumentVersion) -> None:
        services.delete_version(obj)  # also deletes the file

    def delete_queryset(self, request: HttpRequest, queryset: QuerySet[DocumentVersion]) -> None:
        # "Delete selected" in the list. (Django already refuses if one of them was sent.)
        for version in queryset:
            services.delete_version(version)


class ApplicationDocumentForm(forms.ModelForm):
    class Meta:
        model = ApplicationDocument
        fields = ("application", "document_version", "sent_at")

    # The "already sent with this application" check needs no code here: a ModelForm
    # validates the model's UniqueConstraint itself and shows its violation_error_message.
    def clean_sent_at(self) -> datetime:
        sent_at: datetime = self.cleaned_data["sent_at"]
        if sent_at > timezone.now():
            raise forms.ValidationError("The date can't be in the future.")
        return sent_at


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    form = ApplicationDocumentForm
    list_display = ("document_version", "application", "sent_at")
    search_fields = ("document_version__document__title", "application__posting__title")
    list_select_related = ("document_version__document", "application__posting")
    autocomplete_fields = ("application", "document_version")

    # Adding goes through the service (it also writes the timeline event). An existing
    # record is read-only: changing it would no longer match its timeline event.
    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> Any:
        if obj is None:
            return ("created_at", "updated_at")
        return ("application", "document_version", "sent_at", "created_at", "updated_at")

    def save_model(
        self, request: HttpRequest, obj: ApplicationDocument, form: forms.ModelForm, change: bool
    ) -> None:
        if change:
            return  # nothing is editable
        saved = services.attach_version(obj.application, obj.document_version, sent_at=obj.sent_at)
        obj.pk = saved.pk
