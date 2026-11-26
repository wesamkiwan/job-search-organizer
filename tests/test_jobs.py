from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from organizer.jobs.models import JobPosting, Tag, TriageStatus
from tests.factories import CompanyFactory, JobPostingFactory, SourceFactory, TagFactory

pytestmark = pytest.mark.django_db


# --- Tag -------------------------------------------------------------------------------


def test_tag_defaults_and_str() -> None:
    tag = TagFactory.create(name="remote")
    assert tag.color == "neutral"
    assert str(tag) == "remote"


def test_tag_name_is_unique_ignoring_case() -> None:
    TagFactory.create(name="Python")
    with pytest.raises(IntegrityError):
        Tag.objects.create(name="python")


# --- JobPosting: defaults and relations ------------------------------------------------


def test_posting_defaults() -> None:
    posting = JobPostingFactory.create()
    assert posting.triage_status == TriageStatus.NEW
    assert posting.country == "DE"
    assert posting.salary_currency == "EUR"
    assert posting.found_at is not None
    assert posting.custom_data == {}


# Many-to-many works in both directions.
def test_posting_tags_both_directions() -> None:
    remote, python = TagFactory.create(name="remote"), TagFactory.create(name="python")
    posting = JobPostingFactory.create(tags=[remote, python])
    assert set(posting.tags.all()) == {remote, python}
    assert list(remote.postings.all()) == [posting]


# Deleting a company keeps its postings (SET_NULL); the name from the ad is still there.
def test_deleting_company_keeps_postings() -> None:
    posting = JobPostingFactory.create(company_name_raw="Acme GmbH")
    assert posting.company is not None
    posting.company.delete()
    posting.refresh_from_db()
    assert posting.company is None
    assert posting.company_display == "Acme GmbH"


def test_company_display_prefers_linked_company() -> None:
    posting = JobPostingFactory.create(company=CompanyFactory.create(name="Acme"))
    assert posting.company_display == "Acme"
    assert str(posting) == posting.title


# Newest first (ordering = "-found_at").
def test_postings_are_ordered_newest_first() -> None:
    older = JobPostingFactory.create(found_at="2026-01-01T10:00:00+01:00")
    newer = JobPostingFactory.create(found_at="2026-06-01T10:00:00+02:00")
    assert list(JobPosting.objects.all()) == [newer, older]


# --- JobPosting: validation ------------------------------------------------------------


# The database refuses min > max; equal values and open ranges are fine.
@pytest.mark.parametrize(
    ("salary_min", "salary_max", "is_valid"),
    [
        (50_000, 70_000, True),
        (60_000, 60_000, True),
        (None, 70_000, True),
        (50_000, None, True),
        (70_000, 50_000, False),
    ],
)
def test_salary_range_constraint(
    salary_min: int | None, salary_max: int | None, is_valid: bool
) -> None:
    posting = JobPostingFactory.build(
        source=SourceFactory.create(), company=None, salary_min=salary_min, salary_max=salary_max
    )
    if is_valid:
        posting.full_clean()
    else:
        with pytest.raises(ValidationError, match="minimum salary"):
            posting.full_clean()
        with pytest.raises(IntegrityError):
            posting.save()  # even without validation, the database says no


# clean(): "apply until" can't be before the posting date.
def test_valid_through_before_date_posted_is_invalid() -> None:
    posting = JobPostingFactory.build(
        source=SourceFactory.create(),
        company=None,
        date_posted=date(2026, 11, 20),
        valid_through=date(2026, 11, 1),
    )
    with pytest.raises(ValidationError) as error:
        posting.full_clean()
    assert "valid_through" in error.value.message_dict  # the error is on that field


# --- Admin -----------------------------------------------------------------------------


def test_posting_admin_search_by_company(admin_client: Client) -> None:
    JobPostingFactory.create(title="Backend Engineer", company=CompanyFactory.create(name="Acme"))
    JobPostingFactory.create(title="Data Analyst")
    url = reverse("admin:jobs_jobposting_changelist")
    response = admin_client.get(url, {"q": "acme"})  # searches company__name too
    assertContains(response, "Backend Engineer")
    assertNotContains(response, "Data Analyst")


def test_posting_admin_filter_by_status(admin_client: Client) -> None:
    JobPostingFactory.create(title="Saved one", triage_status=TriageStatus.SAVED)
    JobPostingFactory.create(title="New one")
    url = reverse("admin:jobs_jobposting_changelist")
    response = admin_client.get(url, {"triage_status__exact": "saved"})
    assertContains(response, "Saved one")
    assertNotContains(response, "New one")


def test_posting_admin_pages_load(admin_client: Client) -> None:
    posting = JobPostingFactory.create(tags=[TagFactory.create()])
    assert admin_client.get(reverse("admin:jobs_jobposting_add")).status_code == 200
    assert admin_client.get(posting.get_absolute_url()).status_code == 200


def test_tag_admin_shows_posting_count(admin_client: Client) -> None:
    tag = TagFactory.create(name="remote")
    JobPostingFactory.create_batch(2, tags=[tag])
    response = admin_client.get(reverse("admin:jobs_tag_changelist"))
    assert response.context["cl"].result_list[0]._posting_count == 2
