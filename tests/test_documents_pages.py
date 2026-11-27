"""The document pages (list, add, detail, edit, delete, download) and their selectors."""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from organizer.documents import services
from organizer.documents.models import Document, DocumentLanguage, DocumentType, DocumentVersion
from organizer.documents.selectors import document_list, versions_of
from tests.factories import (
    PDF_BYTES,
    ApplicationDocumentFactory,
    DocumentFactory,
    DocumentVersionFactory,
    TagFactory,
)
from tests.sample_files import PNG_BYTES, make_docx, make_pdf

pytestmark = pytest.mark.django_db


def upload(name: str = "cv.pdf", content: bytes = PDF_BYTES) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content)


# --- selectors ---------------------------------------------------------------------------


def test_document_list_counts() -> None:
    document = DocumentFactory.create()
    first, second = DocumentVersionFactory.create_batch(2, document=document)
    # Sent twice with one application and once with another: 2 applications, not 3.
    sent = ApplicationDocumentFactory.create(document_version=first)
    ApplicationDocumentFactory.create(document_version=second, application=sent.application)
    ApplicationDocumentFactory.create(document_version=second)

    row = document_list().get()
    assert row.version_count == 2  # type: ignore[attr-defined]
    assert row.sent_count == 2  # type: ignore[attr-defined]
    assert row.last_upload_at == second.created_at  # type: ignore[attr-defined]


def test_search_finds_text_inside_files_without_duplicates() -> None:
    document = DocumentFactory.create(title="CV EN")
    DocumentVersionFactory.create_batch(3, document=document, extracted_text="Django and HTMX")
    DocumentFactory.create(title="Other")

    found = list(document_list("htmx"))
    assert found == [document]  # once, although 3 versions match
    assert found[0].version_count == 3  # type: ignore[attr-defined]  # not multiplied


@pytest.mark.parametrize(
    "search", ["cv en", "short version", "lebenslauf.pdf", "fixed typo", "backend"]
)
def test_search_fields(search: str) -> None:
    document = DocumentFactory.create(title="CV EN", description="The short version")
    DocumentVersionFactory.create(
        document=document, original_filename="lebenslauf.pdf", change_notes="Fixed typo"
    )
    document.tags.add(TagFactory.create(name="backend"))
    DocumentFactory.create(title="Something else")
    assert list(document_list(search)) == [document]


def test_filters() -> None:
    cv = DocumentFactory.create(language=DocumentLanguage.GERMAN)
    letter = DocumentFactory.create(document_type=DocumentType.objects.get(name="Cover letter"))
    archived = DocumentFactory.create(is_archived=True)

    assert set(document_list()) == {cv, letter}  # archived ones are hidden
    assert set(document_list(show_archived=True)) == {cv, letter, archived}
    assert list(document_list(document_type=letter.document_type)) == [letter]
    assert list(document_list(language="de")) == [cv]
    assert len(document_list(language="nonsense")) == 2  # unknown value → no filter


def test_list_is_grouped_by_type() -> None:
    letter = DocumentFactory.create(
        title="A letter", document_type=DocumentType.objects.get(name="Cover letter")
    )
    cv = DocumentFactory.create(title="Z cv")  # CV comes first (order 10)
    assert list(document_list()) == [cv, letter]


def test_versions_of_newest_first_with_sent_count() -> None:
    document = DocumentFactory.create()
    first, second = DocumentVersionFactory.create_batch(2, document=document)
    ApplicationDocumentFactory.create(document_version=first)
    versions = list(versions_of(document))
    assert versions == [second, first]
    assert [v.sent_count for v in versions] == [0, 1]  # type: ignore[attr-defined]


# --- list page ---------------------------------------------------------------------------


def test_list_page(admin_client: Client) -> None:
    DocumentVersionFactory.create(document__title="CV - Backend (EN)")
    response = admin_client.get(reverse("documents:list"))
    assertContains(response, "CV - Backend (EN)")
    assertContains(response, 'aria-current="page"')  # the sidebar item is active


def test_list_page_empty_states(admin_client: Client) -> None:
    url = reverse("documents:list")
    assertContains(admin_client.get(url), "No documents yet")
    assertContains(admin_client.get(url, {"q": "nothing"}), "No documents match")
    # An invalid filter value is ignored instead of crashing.
    assertContains(admin_client.get(url, {"type": "999"}), "No documents yet")


def test_list_page_filters_and_search(admin_client: Client) -> None:
    DocumentVersionFactory.create(document__title="Wanted", extracted_text="Kubernetes")
    DocumentFactory.create(title="Unwanted")
    response = admin_client.get(reverse("documents:list"), {"q": "kubernetes"})
    assertContains(response, "Wanted")
    assertNotContains(response, "Unwanted")


def test_pages_need_login(client: Client) -> None:
    version = DocumentVersionFactory.create()
    for url in [
        reverse("documents:list"),
        reverse("documents:detail", args=[version.document_id]),
        reverse("documents:download", args=[version.pk]),
    ]:
        response = client.get(url)
        assert response.status_code == 302
        assert response["Location"].startswith(reverse("accounts:login"))


# --- add ---------------------------------------------------------------------------------


def test_add_document_with_its_first_file(admin_client: Client) -> None:
    cv_type = DocumentType.objects.get(name="CV")
    response = admin_client.post(
        reverse("documents:create"),
        {
            "document-title": "CV - Data (DE)",
            "document-document_type": cv_type.pk,
            "document-language": "de",
            "version-file": upload("lebenslauf.pdf", make_pdf("Datenanalyse")),
            "version-change_notes": "First draft",
        },
    )
    document = Document.objects.get()
    assertRedirects(response, document.get_absolute_url())
    version = document.versions.get()
    assert (version.version_number, version.original_filename) == (1, "lebenslauf.pdf")
    assert version.change_notes == "First draft"
    assert version.extracted_text == "Datenanalyse"


def test_add_page_shows_errors_of_both_forms(admin_client: Client) -> None:
    response = admin_client.post(
        reverse("documents:create"),
        {"document-title": "", "version-file": upload("x.exe", b"MZ")},
    )
    assert response.status_code == 200
    assertContains(response, "This field is required.")
    assertContains(response, "Only PDF, Word (.docx), PNG and JPEG files can be uploaded.")
    assert not Document.objects.exists()


def test_add_page_get(admin_client: Client) -> None:
    response = admin_client.get(reverse("documents:create"))
    assertContains(response, 'enctype="multipart/form-data"')
    assertContains(response, 'accept=".pdf,.docx,.png,.jpg,.jpeg"')


def test_no_document_is_left_without_its_file(
    admin_client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the upload fails after the form check (e.g. the same file was stored in the
    meantime), the transaction also undoes the new document."""

    def fail(*args: object, **kwargs: object) -> None:
        raise services.DocumentError("This exact file is already stored.")

    monkeypatch.setattr(services, "upload_version", fail)
    response = admin_client.post(
        reverse("documents:create"),
        {
            "document-title": "CV",
            "document-document_type": DocumentType.objects.get(name="CV").pk,
            "document-language": "en",
            "version-file": upload(),
        },
    )
    assertContains(response, "This exact file is already stored.")
    assert not Document.objects.exists()


# --- detail ------------------------------------------------------------------------------


def test_detail_page(admin_client: Client) -> None:
    document = DocumentFactory.create(title="CV EN", description="For backend jobs")
    old = DocumentVersionFactory.create(document=document, change_notes="First")
    latest = DocumentVersionFactory.create(
        document=document,
        original_filename="photo.png",
        mime_type="image/png",
        extracted_text="",
    )
    ApplicationDocumentFactory.create(document_version=old)
    response = admin_client.get(document.get_absolute_url())

    assertContains(response, "For backend jobs")
    assertContains(response, "photo.png")
    assertContains(response, "Sent with 1 application")
    assertContains(response, "Becomes v3.")
    assertContains(response, "No text found.")
    assertContains(response, f"{reverse('documents:download', args=[latest.pk])}?preview=1")
    # Only the unsent version can be deleted; the document can't (one version was sent).
    assertContains(response, f'id="delete-version-{latest.pk}"')
    assertNotContains(response, f'id="delete-version-{old.pk}"')
    assertContains(response, "This document can&#x27;t be deleted")


def test_detail_page_shows_the_text_and_no_preview_for_word(admin_client: Client) -> None:
    version = DocumentVersionFactory.create(
        mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        original_filename="cv.docx",
        extracted_text="Python Django SQL",
    )
    response = admin_client.get(version.document.get_absolute_url())
    assertContains(response, "Show the text (3 words)")
    assertNotContains(response, "?preview=1")
    assertContains(response, "Delete this document?")


def test_detail_page_without_versions(admin_client: Client) -> None:
    response = admin_client.get(DocumentFactory.create().get_absolute_url())
    assertContains(response, "No files yet.")
    assertContains(response, "Becomes v1.")


def test_unknown_document_is_404(admin_client: Client) -> None:
    assert admin_client.get(reverse("documents:detail", args=[999])).status_code == 404


# --- edit --------------------------------------------------------------------------------


def test_edit_document(admin_client: Client) -> None:
    document = DocumentFactory.create(title="Old")
    url = reverse("documents:edit", args=[document.pk])
    assertContains(admin_client.get(url), "Save changes")
    response = admin_client.post(
        url,
        {
            "title": "New",
            "document_type": document.document_type_id,
            "language": "en",
            "is_archived": "on",
        },
    )
    assertRedirects(response, document.get_absolute_url())
    document.refresh_from_db()
    assert (document.title, document.is_archived) == ("New", True)


# --- actions -----------------------------------------------------------------------------


def test_upload_new_version(admin_client: Client) -> None:
    document = DocumentFactory.create()
    DocumentVersionFactory.create(document=document)
    response = admin_client.post(
        reverse("documents:upload_version", args=[document.pk]),
        {"file": upload("cv.docx", make_docx("Version two")), "change_notes": "New layout"},
        follow=True,
    )
    assertContains(response, "Version 2 uploaded.")
    assert document.latest_version is not None
    assert document.latest_version.extracted_text == "Version two"


def test_upload_errors_become_messages(admin_client: Client) -> None:
    document = DocumentFactory.create()
    url = reverse("documents:upload_version", args=[document.pk])
    response = admin_client.post(url, {"file": upload("photo.png", PNG_BYTES)}, follow=True)
    assertContains(response, "Version 1 uploaded.")
    # The same file again: refused, shown as a message on the detail page.
    response = admin_client.post(url, {"file": upload("again.png", PNG_BYTES)}, follow=True)
    assertContains(response, "This exact file is already stored as version 1")
    # No file at all.
    response = admin_client.post(url, {}, follow=True)
    assertContains(response, "File: This field is required.")


def test_upload_service_error_becomes_a_message(
    admin_client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise services.DocumentError("Something went wrong.")

    monkeypatch.setattr(services, "upload_version", fail)
    document = DocumentFactory.create()
    response = admin_client.post(
        reverse("documents:upload_version", args=[document.pk]), {"file": upload()}, follow=True
    )
    assertContains(response, "Something went wrong.")


def test_upload_needs_post(admin_client: Client) -> None:
    document = DocumentFactory.create()
    assert (
        admin_client.get(reverse("documents:upload_version", args=[document.pk])).status_code == 405
    )


def test_delete_version(admin_client: Client) -> None:
    version = DocumentVersionFactory.create()
    response = admin_client.post(
        reverse("documents:delete_version", args=[version.pk]), follow=True
    )
    assertContains(response, "Version 1 deleted.")
    assert not DocumentVersion.objects.exists()


def test_sent_version_is_not_deleted(admin_client: Client) -> None:
    sent = ApplicationDocumentFactory.create()
    url = reverse("documents:delete_version", args=[sent.document_version_id])
    response = admin_client.post(url, follow=True)
    assertContains(response, "Can&#x27;t delete: sent with 1 application.")
    assert DocumentVersion.objects.exists()


def test_delete_document(admin_client: Client) -> None:
    document = DocumentFactory.create(title="Old CV")
    response = admin_client.post(reverse("documents:delete", args=[document.pk]), follow=True)
    assertContains(response, "“Old CV” and its files deleted.")
    assert not Document.objects.exists()


def test_document_with_sent_version_is_not_deleted(admin_client: Client) -> None:
    sent = ApplicationDocumentFactory.create()
    document = sent.document_version.document
    response = admin_client.post(reverse("documents:delete", args=[document.pk]))
    assertRedirects(response, document.get_absolute_url(), fetch_redirect_response=False)
    assert Document.objects.exists()


# --- download ----------------------------------------------------------------------------


def test_download_sends_the_file_under_its_original_name(admin_client: Client) -> None:
    version = services.upload_version(DocumentFactory.create(), upload("Lebenslauf März.pdf"))
    response = admin_client.get(reverse("documents:download", args=[version.pk]))

    assert response["Content-Type"] == "application/pdf"
    # attachment = "save it"; non-ASCII names (ä) are sent in the encoded filename* form.
    assert response["Content-Disposition"].startswith("attachment;")
    assert "filename*=utf-8''Lebenslauf%20M%C3%A4rz.pdf" in response["Content-Disposition"]
    assert response["Cache-Control"] == "private, no-cache"
    assert response["X-Content-Type-Options"] == "nosniff"
    # FileResponse streams: the body comes in chunks, not as one .content string.
    assert b"".join(response.streaming_content) == PDF_BYTES  # type: ignore[attr-defined]


def test_preview_shows_pdfs_and_images_inline(admin_client: Client) -> None:
    version = DocumentVersionFactory.create()
    url = reverse("documents:download", args=[version.pk])
    response = admin_client.get(url, {"preview": "1"})
    assert response["Content-Disposition"].startswith("inline;")
    # A FileResponse keeps the file open until the response is closed. A web server does
    # that after sending; a test that only looks at the headers must do it itself.
    response.close()


def test_word_files_are_always_downloaded(admin_client: Client) -> None:
    version = services.upload_version(
        DocumentFactory.create(), upload("cv.docx", make_docx("Hello"))
    )
    response = admin_client.get(reverse("documents:download", args=[version.pk]), {"preview": "1"})
    assert response["Content-Disposition"].startswith("attachment;")
    response.close()


def test_files_are_not_public_media_urls(client: Client, media_root: Path) -> None:
    """The stored file can't be reached by its path under /media/ (no such URL exists)."""
    version = DocumentVersionFactory.create()
    assert client.get(f"/media/{version.file.name}").status_code in {302, 404}
