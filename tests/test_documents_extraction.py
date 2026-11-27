import io
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from pypdf import PdfReader, PdfWriter

from organizer.documents import extraction, services
from organizer.documents.extraction import MAX_TEXT_LENGTH, extract_text
from organizer.documents.file_types import DOCX_MIME_TYPE
from organizer.documents.models import DocumentVersion
from tests.factories import DocumentFactory, DocumentVersionFactory
from tests.sample_files import PNG_BYTES, make_docx, make_pdf

pytestmark = pytest.mark.django_db


def test_pdf_text_from_every_page() -> None:
    text = extract_text(io.BytesIO(make_pdf("Python Developer", "Hamburg 2026")), "application/pdf")
    assert text == "Python Developer\nHamburg 2026"


def test_docx_paragraphs_and_tables() -> None:
    content = make_docx("Wesam Example", "", "Backend developer", table=[["Python", "Django"]])
    text = extract_text(io.BytesIO(content), DOCX_MIME_TYPE)
    # The empty paragraph is dropped; table cells are joined with " | ".
    assert text == "Wesam Example\nBackend developer\nPython | Django"


def test_images_have_no_text() -> None:
    assert extract_text(io.BytesIO(PNG_BYTES), "image/png") == ""


def test_broken_files_give_no_text_and_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    # caplog: a pytest fixture that collects what the code wrote to the log.
    file = io.BytesIO(b"%PDF-1.4 this is not really a pdf")
    assert extract_text(file, "application/pdf") == ""
    assert "Could not extract text from a application/pdf file" in caplog.text
    assert file.tell() == 0  # rewound, so the upload can still save it


def test_password_protected_pdf_gives_no_text() -> None:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf("Secret"))))
    writer.encrypt(user_password="geheim", algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    assert extract_text(out, "application/pdf") == ""


def test_pdf_with_empty_password_is_read() -> None:
    # "Encrypted" only against editing: anyone can open it, and so can we.
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf("Open"))))
    writer.encrypt(user_password="", owner_password="owner", algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    assert extract_text(out, "application/pdf") == "Open"


def test_text_is_cleaned_and_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        extraction, "_pdf_text", lambda file: "a\x00b  \n\n  \n" + "x" * MAX_TEXT_LENGTH
    )
    text = extract_text(io.BytesIO(b""), "application/pdf")
    assert text.startswith("ab\nxxx")
    assert len(text) == MAX_TEXT_LENGTH


def test_upload_stores_the_text() -> None:
    upload = SimpleUploadedFile("cv.pdf", make_pdf("Senior Python Developer"))
    version = services.upload_version(DocumentFactory.create(), upload)
    assert version.extracted_text == "Senior Python Developer"
    # The whole file was saved, not only the part after the text was read.
    assert Path(version.file.path).read_bytes() == make_pdf("Senior Python Developer")


def test_command_fills_missing_text() -> None:
    old = DocumentVersionFactory.create(file=ContentFile(make_pdf("Old upload"), name="old.pdf"))
    has_text = DocumentVersionFactory.create(extracted_text="kept")
    out = io.StringIO()
    call_command("extract_document_text", stdout=out)
    old.refresh_from_db()
    has_text.refresh_from_db()
    assert old.extracted_text == "Old upload"
    assert has_text.extracted_text == "kept"  # not touched without --all
    assert "Text updated for 1 version(s)." in out.getvalue()


def test_command_all_reextracts_everything() -> None:
    version = DocumentVersionFactory.create(extracted_text="outdated")  # PDF without text
    call_command("extract_document_text", "--all", stdout=io.StringIO())
    assert DocumentVersion.objects.get(pk=version.pk).extracted_text == ""
    # Running again changes nothing.
    out = io.StringIO()
    call_command("extract_document_text", "--all", stdout=out)
    assert "Text updated for 0 version(s)." in out.getvalue()
