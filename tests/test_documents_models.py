from pathlib import Path

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains

from organizer.documents.models import (
    ApplicationDocument,
    DocumentLanguage,
    DocumentType,
    DocumentVersion,
    version_upload_to,
)
from tests.factories import (
    ApplicationDocumentFactory,
    ApplicationFactory,
    DocumentFactory,
    DocumentTypeFactory,
    DocumentVersionFactory,
    TagFactory,
)

pytestmark = pytest.mark.django_db


# --- DocumentType ------------------------------------------------------------------------


def test_default_document_types_exist_in_order() -> None:
    names = list(DocumentType.objects.values_list("name", flat=True))
    assert names == [
        "CV",
        "Cover letter",
        "Reference letter",
        "Certificate",
        "Portfolio",
        "Photo",
        "Other",
    ]
    assert DocumentType.objects.get(name="CV").description == "Lebenslauf"


def test_document_type_name_is_unique_ignoring_case() -> None:
    with pytest.raises(IntegrityError):
        DocumentType.objects.create(name="cv")


def test_document_type_used_by_documents_cannot_be_deleted() -> None:
    document = DocumentFactory.create()
    with pytest.raises(ProtectedError):
        document.document_type.delete()


# --- Document ----------------------------------------------------------------------------


def test_document_defaults_and_str() -> None:
    document = DocumentFactory.create(title="CV - Backend (EN)")
    assert str(document) == "CV - Backend (EN)"
    assert document.language == DocumentLanguage.ENGLISH
    assert not document.is_archived
    assert document.document_type.name == "CV"


def test_latest_version_is_the_highest_number() -> None:
    document = DocumentFactory.create()
    assert document.latest_version is None
    DocumentVersionFactory.create(document=document)
    newest = DocumentVersionFactory.create(document=document)
    assert newest.version_number == 2
    assert document.latest_version == newest


def test_document_tags() -> None:
    tag = TagFactory.create(name="backend")
    document = DocumentFactory.create(tags=[tag])
    assert list(tag.documents.all()) == [document]


# --- DocumentVersion ---------------------------------------------------------------------


def test_version_str_and_file_on_disk(media_root: Path) -> None:
    version = DocumentVersionFactory.create(document__title="CV - Data (DE)")
    assert str(version) == "CV - Data (DE) v1"
    # The file really exists inside the (temporary) MEDIA_ROOT.
    assert Path(version.file.path).is_relative_to(media_root)
    assert Path(version.file.path).read_bytes().startswith(b"%PDF-")


def test_upload_path_uses_a_random_name_not_the_uploaded_one() -> None:
    version = DocumentVersionFactory.build(document=DocumentFactory.create())
    path = version_upload_to(version, "../../My CV (final).PDF")
    folder, name = path.rsplit("/", 1)
    assert folder == f"documents/{version.document_id}"
    assert name.endswith(".pdf")  # extension kept, lower-cased
    assert len(name) == 32 + 4  # 32 hex characters of the uuid + ".pdf"
    assert ".." not in path and "CV" not in path


def test_version_number_is_unique_per_document() -> None:
    version = DocumentVersionFactory.create()
    with pytest.raises(IntegrityError):
        DocumentVersionFactory.create(document=version.document, version_number=1)


def test_the_same_number_is_fine_in_another_document() -> None:
    DocumentVersionFactory.create()
    other = DocumentVersionFactory.create()
    assert other.version_number == 1


def test_sha256_is_unique() -> None:
    DocumentVersionFactory.create(sha256="a" * 64)
    with pytest.raises(IntegrityError):
        DocumentVersionFactory.create(sha256="a" * 64)


def test_deleting_a_document_deletes_its_unsent_versions() -> None:
    version = DocumentVersionFactory.create()
    version.document.delete()
    assert not DocumentVersion.objects.exists()


# --- ApplicationDocument -----------------------------------------------------------------


def test_sent_version_cannot_be_deleted() -> None:
    sent = ApplicationDocumentFactory.create()
    version = sent.document_version
    assert version.is_sent
    with pytest.raises(ProtectedError):
        version.delete()
    # ...and neither can its document (that would delete the version).
    with pytest.raises(ProtectedError):
        version.document.delete()


def test_unsent_version_is_not_sent() -> None:
    assert not DocumentVersionFactory.create().is_sent


def test_a_version_is_sent_only_once_per_application() -> None:
    sent = ApplicationDocumentFactory.create()
    with pytest.raises(IntegrityError):
        ApplicationDocument.objects.create(
            application=sent.application, document_version=sent.document_version
        )


def test_the_same_version_can_go_to_several_applications() -> None:
    version = DocumentVersionFactory.create()
    ApplicationDocumentFactory.create_batch(2, document_version=version)
    assert version.sent_with.count() == 2


def test_deleting_an_application_keeps_the_document() -> None:
    application = ApplicationFactory.create()
    sent = ApplicationDocumentFactory.create(application=application)
    application.delete()
    assert not ApplicationDocument.objects.exists()
    assert DocumentVersion.objects.filter(pk=sent.document_version_id).exists()


def test_application_document_str() -> None:
    sent = ApplicationDocumentFactory.create(
        document_version__document__title="Cover letter ACME",
        application__posting__title="Python Developer",
    )
    assert str(sent) == "Cover letter ACME v1 → Python Developer"


# --- admin -------------------------------------------------------------------------------


def test_admin_pages_load(admin_client: Client) -> None:
    sent = ApplicationDocumentFactory.create()
    version = sent.document_version
    DocumentTypeFactory.create(name="Transcript")
    urls = [
        reverse("admin:documents_documenttype_changelist"),
        reverse("admin:documents_document_changelist"),
        reverse("admin:documents_document_change", args=[version.document_id]),
        reverse("admin:documents_documentversion_changelist"),
        reverse("admin:documents_documentversion_change", args=[version.pk]),
        reverse("admin:documents_applicationdocument_changelist"),
    ]
    for url in urls:
        assert admin_client.get(url).status_code == 200, url


def test_admin_shows_counts(admin_client: Client) -> None:
    document = DocumentFactory.create(title="CV - counted")
    DocumentVersionFactory.create_batch(2, document=document)
    response = admin_client.get(reverse("admin:documents_document_changelist"))
    counts = {d.title: d._version_count for d in response.context["cl"].result_list}
    assert counts["CV - counted"] == 2
    response = admin_client.get(reverse("admin:documents_documenttype_changelist"))
    type_counts = {t.name: t._document_count for t in response.context["cl"].result_list}
    assert type_counts["CV"] == 1
    assertContains(response, "Lebenslauf")


def test_admin_cannot_add_versions_directly(admin_client: Client) -> None:
    response = admin_client.get(reverse("admin:documents_documentversion_add"))
    assert response.status_code == 403
