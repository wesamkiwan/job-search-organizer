"""Write operations for documents: the ONLY place where versions are created or deleted.

Why a service layer (like applications/services.py)? Uploading a version is more than
`DocumentVersion.objects.create(file=...)`. Every time, wherever the upload comes from
(the admin, the document pages, a future import), the app must:

  - check the file: allowed type (by its CONTENT, not only its name) and size
  - compute its SHA-256 fingerprint and refuse a file that is already stored
  - give it the next version number of its document
  - remember the original name, size and type, and read its text and page count

Deleting must also remove the file from the disk, and must refuse versions that were
sent with an application. Sending a version records it on the application's timeline.
"""

import hashlib
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, transaction
from django.db.models import Max, QuerySet
from django.utils import timezone

from organizer.applications.models import Application, ApplicationEvent, EventKind

from .extraction import read_contents
from .file_types import ALLOWED_TYPES, DOCX_MIME_TYPE, MAGIC_BYTES
from .models import ApplicationDocument, Document, DocumentVersion


class DocumentError(Exception):
    """A business rule was broken. The message is meant for the user (views show it)."""


# --- checking a file ---------------------------------------------------------------------


@dataclass(frozen=True)
class CheckedFile:
    """What check_upload() found out about a file (frozen: can't be changed afterwards)."""

    mime_type: str
    sha256: str
    size_bytes: int
    original_filename: str


def check_upload(file: UploadedFile) -> CheckedFile:
    """Check an uploaded file and compute its fingerprint. Raises DocumentError.

    Forms call this in their clean() method, so the user sees the problem next to the
    file field; upload_version() calls it again, so no upload can skip the checks.
    """
    original_filename = Path(file.name or "").name[:255]
    extension = Path(original_filename).suffix.lower()
    mime_type = ALLOWED_TYPES.get(extension)
    if mime_type is None:
        raise DocumentError("Only PDF, Word (.docx), PNG and JPEG files can be uploaded.")

    size = file.size or 0
    if size == 0:
        raise DocumentError("The file is empty.")
    max_size = settings.DOCUMENT_MAX_UPLOAD_SIZE
    if size > max_size:
        raise DocumentError(f"The file is too large (the limit is {max_size // 1024**2} MB).")

    if not _content_matches(file, mime_type):
        raise DocumentError(f"The file's content is not a real {extension} file.")

    sha256 = compute_sha256(file)
    duplicate = DocumentVersion.objects.filter(sha256=sha256).select_related("document").first()
    if duplicate is not None:
        raise DocumentError(
            f"This exact file is already stored as version {duplicate.version_number} "
            f"of “{duplicate.document.title}”."
        )
    return CheckedFile(mime_type, sha256, size, original_filename)


def compute_sha256(file: UploadedFile) -> str:
    """The file's SHA-256 hash as 64 hex characters.

    file.chunks() reads the file in pieces (64 KB by default) instead of all at once, so
    even a big file never has to fit into memory.
    """
    digest = hashlib.sha256()
    file.seek(0)
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)  # rewind, so the file can be read again (e.g. to save it)
    return digest.hexdigest()


def _content_matches(file: UploadedFile, mime_type: str) -> bool:
    file.seek(0)
    start = file.read(8)
    file.seek(0)
    if not start.startswith(MAGIC_BYTES[mime_type]):
        return False
    if mime_type == DOCX_MIME_TYPE:
        # Every ZIP file starts with "PK". A real Word document is a ZIP that contains
        # word/document.xml.
        try:
            with zipfile.ZipFile(file) as archive:
                return "word/document.xml" in archive.namelist()
        except zipfile.BadZipFile:
            return False
        finally:
            file.seek(0)
    return True


# --- versions ----------------------------------------------------------------------------


@transaction.atomic
def upload_version(
    document: Document, file: UploadedFile, *, change_notes: str = ""
) -> DocumentVersion:
    """Store a file as the next version of a document (v1, v2, ...)."""
    checked = check_upload(file)
    # select_for_update() locks the document's row until the transaction ends, so two
    # uploads at the same moment can't both get the same number. (SQLite locks the whole
    # database on write anyway; PostgreSQL in Phase 8 really needs this.)
    Document.objects.select_for_update().filter(pk=document.pk).first()
    last_number = document.versions.aggregate(last=Max("version_number"))["last"] or 0
    # Read the text and page count now, while we have the file (extraction.py).
    contents = read_contents(file, checked.mime_type)

    version = DocumentVersion(
        document=document,
        version_number=last_number + 1,
        sha256=checked.sha256,
        size_bytes=checked.size_bytes,
        mime_type=checked.mime_type,
        original_filename=checked.original_filename,
        change_notes=change_notes,
        extracted_text=contents.text,
        page_count=contents.page_count,
    )
    version.file.save(checked.original_filename, file, save=False)  # writes the file
    try:
        # A savepoint: if this INSERT fails, only it is undone, and the error can be
        # handled here instead of breaking the whole transaction.
        with transaction.atomic():
            version.save()
    except IntegrityError:
        # The same file was stored between check_upload() and now (very unlikely with
        # one user, but the unique sha256 column guarantees it). The row was not saved,
        # so remove the file we just wrote: no orphan files on disk.
        _delete_file(version.file.name)
        raise DocumentError("This exact file is already stored.") from None
    return version


@transaction.atomic
def delete_version(version: DocumentVersion) -> None:
    """Delete a version and its file. A version that was sent can't be deleted.

    The numbers of the other versions don't change (v1, v3 stay v1, v3): a number that
    you once saw or wrote down must keep meaning the same file.
    """
    _check_not_sent(DocumentVersion.objects.filter(pk=version.pk))
    name = version.file.name
    version.delete()
    _delete_file_on_commit(name)


@transaction.atomic
def delete_document(document: Document) -> None:
    """Delete a document with all its versions and their files."""
    versions = document.versions.all()
    _check_not_sent(versions)
    names = list(versions.values_list("file", flat=True))
    document.delete()  # versions go too (CASCADE)
    for name in names:
        _delete_file_on_commit(name)


def _check_not_sent(versions: QuerySet[DocumentVersion]) -> None:
    sent = ApplicationDocument.objects.filter(document_version__in=versions)
    count = sent.values("application").distinct().count()
    if count:
        raise DocumentError(
            f"Can't delete: sent with {count} application{'s' if count != 1 else ''}. "
            "Archive the document instead."
        )


def _delete_file_on_commit(name: str | None) -> None:
    """Delete a stored file, but only once the database change is really saved.

    on_commit waits for the transaction to succeed. If it is rolled back, the row still
    exists and must keep its file, so the file is NOT deleted. default_storage is the
    storage that FileFields use (configured by the STORAGES setting; MEDIA_ROOT locally).
    """
    transaction.on_commit(lambda: _delete_file(name))


def _delete_file(name: str | None) -> None:
    if name:  # a FieldFile's name is None/"" when there is no file
        default_storage.delete(name)


# --- sending a version with an application -----------------------------------------------


@transaction.atomic
def attach_version(
    application: Application, version: DocumentVersion, *, sent_at: datetime | None = None
) -> ApplicationDocument:
    """Record that a version was sent with an application, and put it on the timeline."""
    when = sent_at or timezone.now()
    if when > timezone.now():
        raise DocumentError("The date can't be in the future.")
    if ApplicationDocument.objects.filter(
        application=application, document_version=version
    ).exists():
        raise DocumentError(f"“{version}” was already sent with this application.")

    sent = ApplicationDocument.objects.create(
        application=application, document_version=version, sent_at=when
    )
    ApplicationEvent.objects.create(
        application=application,
        kind=EventKind.DOCUMENT_SENT,
        occurred_at=when,
        summary=f"Sent “{version}”"[:200],
    )
    return sent
