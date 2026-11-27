"""Forms for the document pages."""

from typing import Any, ClassVar

from django import forms
from django.core.files.uploadedfile import UploadedFile

from organizer.applications.models import Application
from organizer.core.forms import DateTimeInput, now_for_input

from . import services
from .file_types import ALLOWED_TYPES
from .models import Document, DocumentLanguage, DocumentType, DocumentVersion
from .selectors import sendable_versions


class DocumentForm(forms.ModelForm):
    wide_fields = ("title", "tags", "description", "is_archived")

    class Meta:
        model = Document
        fields = ("title", "document_type", "language", "tags", "description", "is_archived")
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "title": forms.TextInput(attrs={"placeholder": "e.g. CV - Backend Developer (EN)"}),
            "tags": forms.CheckboxSelectMultiple(),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class VersionUploadForm(forms.Form):
    """Upload a file as a new version. Also the "first file" part of the add page."""

    file = forms.FileField(
        # An explicit label: Django only derives "File" from the name when rendering, and
        # form_errors_to_messages needs it for "File: This field is required.".
        label="File",
        # accept: the browser's file picker shows only these types (a convenience only;
        # anyone can still send any file, so the server checks it in clean_file).
        widget=forms.FileInput(attrs={"accept": ",".join(ALLOWED_TYPES)}),
        help_text="PDF, Word (.docx), PNG or JPEG.",
    )
    change_notes = forms.CharField(
        label="What changed?",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def clean_file(self) -> UploadedFile:
        file: UploadedFile = self.cleaned_data["file"]
        try:
            services.check_upload(file)
        except services.DocumentError as error:
            raise forms.ValidationError(str(error)) from error
        return file


class DocumentFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=100)
    # ModelChoiceField: the options come from the database (all document types), and
    # cleaned_data["type"] is a DocumentType object (or None for "All types").
    type = forms.ModelChoiceField(
        queryset=DocumentType.objects.all(), required=False, empty_label="All types"
    )
    language = forms.ChoiceField(
        choices=(("", "All languages"), *DocumentLanguage.choices), required=False
    )
    archived = forms.BooleanField(required=False, label="Show archived")

    def values(self) -> dict[str, Any]:
        """The filters as keyword arguments for selectors.document_list()."""
        self.is_valid()  # invalid values (e.g. an unknown type id) are simply ignored
        data = getattr(self, "cleaned_data", {})
        return {
            "search": data.get("q") or "",
            "document_type": data.get("type"),
            "language": data.get("language") or "",
            "show_archived": bool(data.get("archived")),
        }

    @property
    def is_filtered(self) -> bool:
        return any(self.values().values())


class VersionChoiceField(forms.ModelChoiceField):
    """A dropdown of document versions, labelled "CV - Backend (EN) · v2 · cv.pdf"."""

    # label_from_instance: how ModelChoiceField turns each object into the option's text.
    def label_from_instance(self, obj: DocumentVersion) -> str:
        return f"{obj.document.title} · v{obj.version_number} · {obj.original_filename}"


class SendDocumentForm(forms.Form):
    """Record that a document version was sent with an application."""

    version = VersionChoiceField(
        queryset=DocumentVersion.objects.none(),  # set per application in __init__
        label="Document",
        empty_label="Choose a document version",
    )
    sent_at = forms.DateTimeField(label="Sent on", widget=DateTimeInput(), initial=now_for_input)

    def __init__(self, *args: Any, application: Application, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["version"].queryset = sendable_versions(application)  # type: ignore[attr-defined]
