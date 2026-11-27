import hashlib
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import Settings
from pytest_django.asserts import assertContains

from organizer.applications.models import EventKind
from organizer.documents import services
from organizer.documents.file_types import DOCX_MIME_TYPE
from organizer.documents.models import ApplicationDocument, DocumentVersion
from organizer.documents.services import DocumentError
from tests.factories import (
    PDF_BYTES,
    ApplicationDocumentFactory,
    ApplicationFactory,
    DocumentFactory,
    DocumentVersionFactory,
)
from tests.sample_files import JPEG_BYTES, PNG_BYTES, make_zip

pytestmark = pytest.mark.django_db

# The type of pytest-django's django_capture_on_commit_callbacks fixture (renamed below).
OnCommit = Callable[..., AbstractContextManager[list[Callable[[], object]]]]


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks: OnCommit) -> OnCommit:
    """A shorter name for pytest-django's django_capture_on_commit_callbacks."""
    return django_capture_on_commit_callbacks


def upload(name: str = "cv.pdf", content: bytes = PDF_BYTES) -> SimpleUploadedFile:
    """A file as Django gives it to a view after an upload (request.FILES["file"])."""
    return SimpleUploadedFile(name, content)


# --- check_upload ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "content", "mime_type"),
    [
        ("cv.pdf", PDF_BYTES, "application/pdf"),
        ("CV.PDF", PDF_BYTES, "application/pdf"),  # extension case doesn't matter
        ("letter.docx", make_zip("word/document.xml"), DOCX_MIME_TYPE),
        ("photo.png", PNG_BYTES, "image/png"),
        ("photo.jpg", JPEG_BYTES, "image/jpeg"),
        ("photo.jpeg", JPEG_BYTES, "image/jpeg"),
    ],
)
def test_allowed_files_pass_the_check(name: str, content: bytes, mime_type: str) -> None:
    checked = services.check_upload(upload(name, content))
    assert checked.mime_type == mime_type
    assert checked.size_bytes == len(content)
    assert checked.original_filename == name
    assert len(checked.sha256) == 64


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("cv.doc", PDF_BYTES, "Only PDF, Word"),  # old Word format: not allowed
        ("script.exe", b"MZ", "Only PDF, Word"),
        ("no-extension", PDF_BYTES, "Only PDF, Word"),
        ("empty.pdf", b"", "empty"),
        ("fake.pdf", b"MZ this is a program", "not a real .pdf"),  # renamed file
        ("fake.png", JPEG_BYTES, "not a real .png"),
        ("archive.docx", make_zip("something.txt"), "not a real .docx"),  # a ZIP, not Word
        ("broken.docx", b"PK\x03\x04 not really a zip", "not a real .docx"),
    ],
)
def test_bad_files_are_refused(name: str, content: bytes, message: str) -> None:
    with pytest.raises(DocumentError, match=message):
        services.check_upload(upload(name, content))


def test_too_large_files_are_refused(settings: Settings) -> None:
    settings.DOCUMENT_MAX_UPLOAD_SIZE = 1024 * 1024  # 1 MB for this test
    big = PDF_BYTES + b"x" * (1024 * 1024)
    with pytest.raises(DocumentError, match=r"too large \(the limit is 1 MB\)"):
        services.check_upload(upload("big.pdf", big))


def test_path_parts_are_removed_from_the_original_name() -> None:
    checked = services.check_upload(upload("../../secret/cv.pdf"))
    assert checked.original_filename == "cv.pdf"


def test_sha256_is_the_real_hash() -> None:
    assert services.compute_sha256(upload()) == hashlib.sha256(PDF_BYTES).hexdigest()


# --- upload_version ----------------------------------------------------------------------


def test_upload_creates_numbered_versions(media_root: Path) -> None:
    document = DocumentFactory.create()
    first = services.upload_version(document, upload("cv-october.pdf"), change_notes="First")
    second = services.upload_version(document, upload("cv-november.pdf", PDF_BYTES + b"v2"))

    assert (first.version_number, second.version_number) == (1, 2)
    assert first.original_filename == "cv-october.pdf"
    assert first.change_notes == "First"
    assert first.mime_type == "application/pdf"
    assert first.size_bytes == len(PDF_BYTES)
    # The file is stored under a random name, with the right content.
    stored = Path(first.file.path)
    assert stored.is_relative_to(media_root / "documents" / str(document.pk))
    assert stored.name != "cv-october.pdf"
    assert stored.read_bytes() == PDF_BYTES


def test_numbers_continue_after_the_highest_one() -> None:
    document = DocumentFactory.create()
    DocumentVersionFactory.create(document=document, version_number=5)
    assert services.upload_version(document, upload()).version_number == 6


def test_the_same_file_is_refused_even_for_another_document() -> None:
    services.upload_version(DocumentFactory.create(title="CV EN"), upload("a.pdf"))
    with pytest.raises(DocumentError, match="already stored as version 1 of “CV EN”"):
        services.upload_version(DocumentFactory.create(), upload("renamed.pdf"))
    assert DocumentVersion.objects.count() == 1


def test_upload_checks_the_file_too() -> None:
    with pytest.raises(DocumentError):
        services.upload_version(DocumentFactory.create(), upload("x.exe", b"MZ"))
    assert not DocumentVersion.objects.exists()


def test_duplicate_saved_at_the_same_moment_leaves_no_file(
    media_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rare race: another upload stores the same file just after our check. Then the
    database's unique sha256 refuses our row, and the file we wrote is removed again."""
    existing = services.upload_version(DocumentFactory.create(), upload())

    # monkeypatch replaces something for this one test only. Here: a check that does
    # NOT look for duplicates, as if the other upload happened right after it.
    def check_without_duplicate_lookup(file: SimpleUploadedFile) -> services.CheckedFile:
        return services.CheckedFile(
            "application/pdf", services.compute_sha256(file), len(PDF_BYTES), "cv.pdf"
        )

    monkeypatch.setattr(services, "check_upload", check_without_duplicate_lookup)
    with pytest.raises(DocumentError, match="already stored"):
        services.upload_version(DocumentFactory.create(), upload())

    files = list((media_root / "documents").rglob("*.pdf"))
    assert files == [Path(existing.file.path)]  # only the first upload's file is left


# --- delete_version / delete_document ----------------------------------------------------


def test_delete_version_removes_row_and_file(on_commit: OnCommit) -> None:
    version = services.upload_version(DocumentFactory.create(), upload())
    path = Path(version.file.path)
    # In tests each test runs inside a transaction that is rolled back at the end, never
    # committed, so on_commit functions would never run. This fixture collects them and
    # (execute=True) runs them at the end of the with-block, as a real commit would.
    with on_commit(execute=True):
        services.delete_version(version)
    assert not DocumentVersion.objects.exists()
    assert not path.exists()


def test_other_numbers_stay_after_a_delete() -> None:
    document = DocumentFactory.create()
    second = DocumentVersionFactory.create_batch(3, document=document)[1]
    services.delete_version(second)
    numbers = sorted(document.versions.values_list("version_number", flat=True))
    assert numbers == [1, 3]


def test_sent_version_cannot_be_deleted() -> None:
    sent = ApplicationDocumentFactory.create()
    with pytest.raises(DocumentError, match="sent with 1 application\\. Archive"):
        services.delete_version(sent.document_version)
    assert DocumentVersion.objects.filter(pk=sent.document_version_id).exists()


def test_delete_document_removes_all_files(on_commit: OnCommit) -> None:
    document = DocumentFactory.create()
    paths = [
        Path(
            services.upload_version(document, upload(f"v{n}.pdf", PDF_BYTES + bytes([n]))).file.path
        )
        for n in range(2)
    ]
    with on_commit(execute=True):
        services.delete_document(document)
    assert not any(path.exists() for path in paths)
    assert not DocumentVersion.objects.exists()


def test_document_with_sent_versions_cannot_be_deleted() -> None:
    document = DocumentFactory.create()
    version = DocumentVersionFactory.create(document=document)
    ApplicationDocumentFactory.create_batch(2, document_version=version)
    with pytest.raises(DocumentError, match="sent with 2 applications"):
        services.delete_document(document)


def test_file_stays_if_the_delete_is_rolled_back() -> None:
    version = services.upload_version(DocumentFactory.create(), upload())
    path, pk = Path(version.file.path), version.pk  # delete() sets version.pk to None
    with pytest.raises(RuntimeError), transaction.atomic():
        services.delete_version(version)
        raise RuntimeError("something later failed")
    # The rollback undid the delete, so the row is back and its file must still exist.
    assert path.exists()
    assert DocumentVersion.objects.filter(pk=pk).exists()


def test_deleting_without_a_file_name_does_nothing(on_commit: OnCommit) -> None:
    # A FieldFile without a file has an empty name; there is nothing to delete then.
    version = DocumentVersionFactory.create(file="")
    with on_commit(execute=True):
        services.delete_version(version)
    assert not DocumentVersion.objects.exists()


# --- attach_version ----------------------------------------------------------------------


def test_attach_records_the_send_and_the_timeline_event() -> None:
    application = ApplicationFactory.create()
    version = DocumentVersionFactory.create(document__title="CV EN")
    when = timezone.now() - timedelta(days=2)

    sent = services.attach_version(application, version, sent_at=when)

    assert sent.sent_at == when
    event = application.events.get()
    assert event.kind == EventKind.DOCUMENT_SENT
    assert event.occurred_at == when
    assert event.summary == "Sent “CV EN v1”"


def test_attach_defaults_to_now() -> None:
    sent = services.attach_version(ApplicationFactory.create(), DocumentVersionFactory.create())
    assert timezone.now() - sent.sent_at < timedelta(seconds=5)


def test_attach_refuses_a_future_date() -> None:
    with pytest.raises(DocumentError, match="future"):
        services.attach_version(
            ApplicationFactory.create(),
            DocumentVersionFactory.create(),
            sent_at=timezone.now() + timedelta(hours=1),
        )


def test_attach_refuses_the_same_version_twice() -> None:
    sent = ApplicationDocumentFactory.create()
    with pytest.raises(DocumentError, match="already sent"):
        services.attach_version(sent.application, sent.document_version)
    assert ApplicationDocument.objects.count() == 1


# --- admin (uses the services) -----------------------------------------------------------


def test_admin_upload_creates_a_version(admin_client: Client) -> None:
    document = DocumentFactory.create()
    response = admin_client.post(
        reverse("admin:documents_documentversion_add"),
        {"document": document.pk, "file": upload("cv.pdf"), "change_notes": "Shorter"},
    )
    assert response.status_code == 302
    version = document.versions.get()
    assert (version.version_number, version.change_notes) == (1, "Shorter")
    # The admin's success message names the saved version (it was reloaded).
    messages = [str(m) for m in response.wsgi_request._messages]  # type: ignore[attr-defined]
    assert f"{document.title} v1" in messages[0]


def test_admin_upload_shows_the_problem_next_to_the_field(admin_client: Client) -> None:
    response = admin_client.post(
        reverse("admin:documents_documentversion_add"),
        {"document": DocumentFactory.create().pk, "file": upload("x.exe", b"MZ")},
    )
    assert response.status_code == 200  # the form again, with the error
    assertContains(response, "Only PDF, Word (.docx), PNG and JPEG files can be uploaded.")
    assert not DocumentVersion.objects.exists()


def test_admin_change_page_only_edits_the_notes(admin_client: Client) -> None:
    version = DocumentVersionFactory.create(change_notes="old")
    url = reverse("admin:documents_documentversion_change", args=[version.pk])
    response = admin_client.post(url, {"change_notes": "new", "version_number": 99})
    assert response.status_code == 302
    version.refresh_from_db()
    assert (version.change_notes, version.version_number) == ("new", 1)


def test_admin_delete_removes_the_file(admin_client: Client, on_commit: OnCommit) -> None:
    version = services.upload_version(DocumentFactory.create(), upload())
    path = Path(version.file.path)
    url = reverse("admin:documents_documentversion_delete", args=[version.pk])
    with on_commit(execute=True):
        admin_client.post(url, {"post": "yes"})
    assert not path.exists()


def test_admin_bulk_delete_of_versions_and_documents(
    admin_client: Client, on_commit: OnCommit
) -> None:
    versions = [
        services.upload_version(DocumentFactory.create(), upload(content=PDF_BYTES + bytes([n])))
        for n in range(3)
    ]
    with on_commit(execute=True):
        admin_client.post(
            reverse("admin:documents_documentversion_changelist"),
            {"action": "delete_selected", "_selected_action": [versions[0].pk], "post": "yes"},
        )
        admin_client.post(
            reverse("admin:documents_document_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [versions[1].document_id],
                "post": "yes",
            },
        )
    assert list(DocumentVersion.objects.all()) == [versions[2]]
    assert [p.name for p in Path(versions[2].file.path).parent.parent.rglob("*.pdf")] == [
        Path(versions[2].file.path).name
    ]


def test_admin_delete_document(admin_client: Client, on_commit: OnCommit) -> None:
    version = services.upload_version(DocumentFactory.create(), upload())
    url = reverse("admin:documents_document_delete", args=[version.document_id])
    with on_commit(execute=True):
        admin_client.post(url, {"post": "yes"})
    assert not Path(version.file.path).exists()


def test_admin_hides_delete_for_sent_versions(admin_client: Client) -> None:
    sent = ApplicationDocumentFactory.create()
    url = reverse("admin:documents_documentversion_delete", args=[sent.document_version_id])
    assert admin_client.get(url).status_code == 403


def test_admin_attach_writes_the_timeline_event(admin_client: Client) -> None:
    application = ApplicationFactory.create()
    version = DocumentVersionFactory.create()
    now = timezone.localtime()
    response = admin_client.post(
        reverse("admin:documents_applicationdocument_add"),
        {
            "application": application.pk,
            "document_version": version.pk,
            "sent_at_0": now.strftime("%Y-%m-%d"),
            "sent_at_1": "00:00:00",
        },
    )
    assert response.status_code == 302
    assert application.events.get().kind == EventKind.DOCUMENT_SENT
    sent = ApplicationDocument.objects.get()
    # The change page is read-only and saving it changes nothing.
    change_url = reverse("admin:documents_applicationdocument_change", args=[sent.pk])
    assert admin_client.post(change_url, {}).status_code == 302
    assert ApplicationDocument.objects.get().sent_at == sent.sent_at


def test_admin_attach_refuses_a_future_date(admin_client: Client) -> None:
    tomorrow = timezone.localtime() + timedelta(days=1)
    response = admin_client.post(
        reverse("admin:documents_applicationdocument_add"),
        {
            "application": ApplicationFactory.create().pk,
            "document_version": DocumentVersionFactory.create().pk,
            "sent_at_0": tomorrow.strftime("%Y-%m-%d"),
            "sent_at_1": "12:00:00",
        },
    )
    assertContains(response, "The date can&#x27;t be in the future.")
