"""Your application documents (CVs, cover letters, references...) and their versions.

The idea in one picture:

    Document "CV - Backend Developer (EN)"      <- the logical document (title, type, ...)
      ├── DocumentVersion v1  cv-2026-10.pdf     <- one uploaded file each, never changed
      ├── DocumentVersion v2  cv-2026-11.pdf
      └── DocumentVersion v3  cv-final.pdf  ──── ApplicationDocument ──── Application
                                                  ("sent to company X on 12.11.")

Important rule: versions are ONLY created and deleted through services.py
(upload_version, delete_version, ...). The services check the file, compute its
fingerprint, number the versions and clean up the files on disk.
"""

from pathlib import Path
from uuid import uuid4

from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone

from organizer.applications.models import Application
from organizer.core.models import TimeStampedModel
from organizer.jobs.models import Tag

# --- DocumentType ------------------------------------------------------------------------


class DocumentType(TimeStampedModel):
    """A kind of document: CV, Cover letter, Reference letter, ... (editable in the admin)."""

    name = models.CharField(max_length=50)
    description = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=0, help_text="Smaller numbers come first.")

    class Meta:
        ordering = ("order", "name")
        constraints = (
            models.UniqueConstraint(
                Lower("name"),
                name="document_type_name_unique_ignoring_case",
                violation_error_message="A document type with this name already exists.",
            ),
        )

    def __str__(self) -> str:
        return self.name


# --- Document ----------------------------------------------------------------------------


class DocumentLanguage(models.TextChoices):
    GERMAN = "de", "German"
    ENGLISH = "en", "English"
    OTHER = "other", "Other"


class Document(TimeStampedModel):
    """A logical document, e.g. "CV - Backend Developer (EN)". The files are its versions."""

    title = models.CharField(max_length=200)
    # PROTECT: a type that documents use can't be deleted (they would lose their type).
    document_type = models.ForeignKey(
        DocumentType, on_delete=models.PROTECT, related_name="documents", verbose_name="type"
    )
    language = models.CharField(
        max_length=10, choices=DocumentLanguage.choices, default=DocumentLanguage.ENGLISH
    )
    description = models.TextField(blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="documents")
    is_archived = models.BooleanField(
        "archived", default=False, help_text="Hidden from lists, but kept with its history."
    )

    class Meta:
        ordering = ("title", "pk")

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("documents:detail", args=[self.pk])

    @property
    def latest_version(self) -> "DocumentVersion | None":
        # One query. Pages that list many documents will use a prefetch instead (batch B).
        return self.versions.order_by("-version_number").first()


# --- DocumentVersion ---------------------------------------------------------------------


# Formats every browser can display itself. A Word file is always downloaded.
PREVIEW_MIME_TYPES = frozenset({"application/pdf", "image/png", "image/jpeg"})


def version_upload_to(instance: "DocumentVersion", filename: str) -> str:
    """Where a version's file is stored, relative to MEDIA_ROOT.

    Django calls this function when the file is saved. We do NOT use the uploaded name
    on disk: names like "../../settings.py" or "CV (final) ä.pdf" cause trouble. A random
    name (uuid4) is always safe and can't be guessed. The real name is kept in the
    original_filename column and given back when you download the file.

    Example result: "documents/7/3f2a9c0d4e5b4f6a8b7c9d0e1f2a3b4c.pdf"
    """
    extension = Path(filename).suffix.lower()
    return f"documents/{instance.document_id}/{uuid4().hex}{extension}"


class DocumentVersion(TimeStampedModel):
    """One uploaded file of a document. Never changes after upload (only change_notes)."""

    # CASCADE: versions belong to their document. (A version that was sent with an
    # application is still protected, see ApplicationDocument.document_version.)
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField(editable=False)
    # FileField stores only the PATH in the database ("documents/7/3f2a....pdf"); the file
    # itself goes to the storage (by default the MEDIA_ROOT folder on disk).
    file = models.FileField(upload_to=version_upload_to, max_length=255)
    # The file's fingerprint (SHA-256 hash, 64 hex characters). Two files have the same
    # hash only if they are byte-for-byte identical, so this finds re-uploads of the same
    # file. unique=True: the database itself refuses a second copy, as a last safety net.
    sha256 = models.CharField("SHA-256", max_length=64, unique=True, editable=False)
    size_bytes = models.PositiveBigIntegerField("size (bytes)", editable=False)
    mime_type = models.CharField("MIME type", max_length=100, editable=False)
    original_filename = models.CharField(max_length=255, editable=False)
    # Plain text taken out of PDF / DOCX files (batch B): for search and future AI features.
    extracted_text = models.TextField(blank=True, editable=False)
    change_notes = models.TextField(blank=True, help_text="What changed in this version?")

    class Meta:
        ordering = ("document", "-version_number")  # newest version first
        constraints = (
            models.UniqueConstraint(
                fields=("document", "version_number"), name="unique_version_number_per_document"
            ),
        )

    def __str__(self) -> str:
        # Uses the document: lists of versions should select_related("document").
        return f"{self.document.title} v{self.version_number}"

    @property
    def can_preview(self) -> bool:
        """Can the browser show this file itself (in a new tab), instead of downloading it?"""
        return self.mime_type in PREVIEW_MIME_TYPES

    @property
    def is_sent(self) -> bool:
        """Was this version sent with at least one application? Then it can't be deleted."""
        return self.sent_with.exists()


# --- ApplicationDocument -----------------------------------------------------------------


class ApplicationDocument(TimeStampedModel):
    """ "This version of this document was sent with this application, on this date."

    This is the "through" table between applications and document versions. It is a
    model of its own (not a plain ManyToManyField) because the link carries data: sent_at.
    """

    # CASCADE: deleting an application removes its "sent" records (not the documents).
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="sent_documents"
    )
    # PROTECT: a version that was sent can't be deleted; you'd lose the proof of what you
    # sent. Django raises ProtectedError if anything tries.
    document_version = models.ForeignKey(
        DocumentVersion, on_delete=models.PROTECT, related_name="sent_with"
    )
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-sent_at", "-pk")
        constraints = (
            models.UniqueConstraint(
                fields=("application", "document_version"),
                name="document_version_sent_once_per_application",
                violation_error_message="This version was already sent with this application.",
            ),
        )

    def __str__(self) -> str:
        return f"{self.document_version} → {self.application}"
