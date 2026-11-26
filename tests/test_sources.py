import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains

from organizer.sources.models import Source, SourceKind
from tests.factories import JobPostingFactory, SourceFactory

pytestmark = pytest.mark.django_db


# The data migration created the defaults (pytest-django runs all migrations when it
# creates the test database, so this really tests the migration).
def test_default_sources_exist() -> None:
    names = set(Source.objects.values_list("name", flat=True))
    assert {"Manual", "StepStone", "LinkedIn"} <= names  # <= on sets: "is a subset of"
    assert Source.objects.get(name="StepStone").website == "https://www.stepstone.de"


def test_source_defaults() -> None:
    source = SourceFactory.create()
    assert source.kind == SourceKind.MANUAL
    assert source.is_enabled
    assert str(source) == source.name


def test_source_name_is_unique_ignoring_case() -> None:
    with pytest.raises(IntegrityError):
        Source.objects.create(name="stepstone")


# on_delete=PROTECT: a source that postings point to can't be deleted.
def test_source_used_by_postings_cannot_be_deleted() -> None:
    posting = JobPostingFactory.create()
    with pytest.raises(ProtectedError):
        posting.source.delete()


def test_source_admin_shows_posting_count(admin_client: Client) -> None:
    JobPostingFactory.create_batch(3, source=SourceFactory.create(name="StepStone"))
    response = admin_client.get(reverse("admin:sources_source_changelist"))
    counts = {s.name: s._posting_count for s in response.context["cl"].result_list}
    assert counts["StepStone"] == 3
    assertContains(response, "LinkedIn")
