import io
import re
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from pypdf import PdfReader, PdfWriter

from organizer.documents import extraction, services
from organizer.documents.extraction import MAX_TEXT_LENGTH, FileContents, read_contents
from organizer.documents.file_types import DOCX_MIME_TYPE
from organizer.documents.models import DocumentVersion
from tests.factories import DocumentFactory, DocumentVersionFactory
from tests.sample_files import PNG_BYTES, make_docx, make_pdf, make_zip

pytestmark = pytest.mark.django_db


def read_pdf(content: bytes) -> FileContents:
    return read_contents(io.BytesIO(content), "application/pdf")


def read_docx(content: bytes) -> FileContents:
    return read_contents(io.BytesIO(content), DOCX_MIME_TYPE)


def encrypted_pdf(text: str, *, user_password: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf(text))))
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm="AES-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# --- PDF -----------------------------------------------------------------------------------


def test_pdf_text_and_pages() -> None:
    contents = read_pdf(make_pdf("Python Developer", "Hamburg 2026"))
    assert contents == FileContents("Python Developer\nHamburg 2026", page_count=2)


def test_password_protected_pdf_gives_nothing() -> None:
    assert read_pdf(encrypted_pdf("Secret", user_password="geheim")) == FileContents()


def test_pdf_with_empty_password_is_read() -> None:
    # "Encrypted" only against editing: anyone can open it, and so can we.
    assert read_pdf(encrypted_pdf("Open", user_password="")) == FileContents("Open", 1)


# --- Word ----------------------------------------------------------------------------------


def test_docx_paragraphs_tables_and_pages() -> None:
    content = make_docx(
        "Wesam Example", "", "Backend developer", table=[["Python", "Django"]], pages=4
    )
    # The empty paragraph is dropped; table cells are joined with " | ".
    assert read_docx(content) == FileContents(
        "Wesam Example\nBackend developer\nPython | Django", page_count=4
    )


@pytest.mark.parametrize("pages", [None, 0])
def test_docx_without_a_page_count_is_unknown(pages: int | None) -> None:
    # None: no metadata file at all. 0: a number, but not a real page count.
    # The text proves the file itself was read fine (not an error that hid everything).
    assert read_docx(make_docx("Text", pages=pages)) == FileContents("Text", None)


def test_docx_metadata_without_pages_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    # Some programs write docProps/app.xml without a <Pages> entry: the search finds nothing.
    monkeypatch.setattr(extraction, "WORD_PAGES", re.compile(rb"<NoSuchTag>(\d+)<"))
    assert read_docx(make_docx("Text", pages=3)) == FileContents("Text", None)


# --- other files and errors ----------------------------------------------------------------


def test_images_are_one_page_without_text() -> None:
    assert read_contents(io.BytesIO(PNG_BYTES), "image/png") == FileContents(page_count=1)


def test_unknown_types_give_nothing() -> None:
    assert read_contents(io.BytesIO(b"x"), "text/plain") == FileContents()


@pytest.mark.parametrize(
    ("content", "mime_type"),
    [
        (b"%PDF-1.4 this is not really a pdf", "application/pdf"),
        (make_zip("word/document.xml"), DOCX_MIME_TYPE),  # a ZIP, but not a real Word file
    ],
)
def test_broken_files_give_nothing_and_are_logged(
    content: bytes, mime_type: str, caplog: pytest.LogCaptureFixture
) -> None:
    # caplog: a pytest fixture that collects what the code wrote to the log.
    file = io.BytesIO(content)
    assert read_contents(file, mime_type) == FileContents()
    assert f"Could not read the contents of a {mime_type} file" in caplog.text
    assert file.tell() == 0  # rewound, so the upload can still save it


def test_text_is_cleaned_and_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = "a\x00b  \n\n  \n" + "x" * MAX_TEXT_LENGTH  # a NUL, trailing spaces, empty lines
    monkeypatch.setattr(extraction, "_read_pdf", lambda file: FileContents(raw, 1))
    contents = read_pdf(b"")
    assert contents.text.startswith("ab\nxxx")
    assert len(contents.text) == MAX_TEXT_LENGTH
    assert contents.page_count == 1


# --- upload and command --------------------------------------------------------------------


def test_upload_stores_text_and_pages() -> None:
    content = make_pdf("Senior Python Developer", "Page two")
    version = services.upload_version(
        DocumentFactory.create(), SimpleUploadedFile("cv.pdf", content)
    )
    assert version.extracted_text == "Senior Python Developer\nPage two"
    assert version.page_count == 2
    # The whole file was saved, not only the part after it was read.
    assert Path(version.file.path).read_bytes() == content


def test_command_fills_gaps() -> None:
    no_text = DocumentVersionFactory.create(
        file=ContentFile(make_pdf("Old upload"), name="old.pdf"), page_count=1
    )
    no_pages = DocumentVersionFactory.create(
        file=ContentFile(make_pdf("Has text", "2"), name="b.pdf"), extracted_text="Has text\n2"
    )
    complete = DocumentVersionFactory.create(extracted_text="kept", page_count=9)
    out = io.StringIO()
    call_command("extract_document_text", stdout=out)

    for version in (no_text, no_pages, complete):
        version.refresh_from_db()
    assert (no_text.extracted_text, no_text.page_count) == ("Old upload", 1)
    assert no_pages.page_count == 2
    assert (complete.extracted_text, complete.page_count) == ("kept", 9)  # not touched
    assert "Updated 2 version(s)." in out.getvalue()


def test_command_all_rereads_everything() -> None:
    # The factory's tiny PDF has no text and no pages: both become unknown.
    version = DocumentVersionFactory.create(extracted_text="outdated", page_count=7)
    call_command("extract_document_text", "--all", stdout=io.StringIO())
    version = DocumentVersion.objects.get(pk=version.pk)
    assert (version.extracted_text, version.page_count) == ("", None)
    # Running again changes nothing.
    out = io.StringIO()
    call_command("extract_document_text", "--all", stdout=out)
    assert "Updated 0 version(s)." in out.getvalue()
