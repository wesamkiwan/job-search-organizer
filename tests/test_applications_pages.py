"""Add, edit and detail pages of applications, and the actions on the detail page."""

from datetime import timedelta
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from organizer.applications import services
from organizer.applications.forms import PostingForm
from organizer.applications.models import Application, EventKind
from organizer.companies.models import Company
from organizer.companies.services import find_or_create_company
from organizer.jobs.models import JobPosting, TriageStatus
from tests.factories import (
    ApplicationFactory,
    CompanyFactory,
    JobPostingFactory,
    SourceFactory,
    TagFactory,
    stage,
)

pytestmark = pytest.mark.django_db

CREATE_URL = reverse("applications:create")


def create_data(**overrides: Any) -> dict[str, Any]:
    """A valid POST for the add page. Field names carry the form prefixes."""
    data = {
        "posting-title": "Backend Developer",
        "posting-company_name": "Acme GmbH",
        "posting-source": SourceFactory.create(name="StepStone").pk,
        "posting-salary_currency": "EUR",
        "posting-salary_period": "year",
        "application-stage": stage("Applied").pk,
        "application-priority": "medium",
        "application-salary_expectation_currency": "EUR",
    }
    data.update(overrides)
    return data


def started(**fields: Any) -> Application:
    """An application created through the service (so it has its first event)."""
    application = ApplicationFactory.build(posting=JobPostingFactory.create(), **fields)
    return services.create_application(application)


def when(days_ago: int = 0) -> str:
    """A datetime-local form value."""
    return (timezone.localtime() - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M")


# --- find_or_create_company ------------------------------------------------------------


def test_find_or_create_company() -> None:
    acme = CompanyFactory.create(name="ACME GmbH")
    assert find_or_create_company("  acme   gmbh ") == acme  # case and spaces ignored
    new = find_or_create_company("Globex")
    assert new is not None
    assert new.name == "Globex"
    assert find_or_create_company("   ") is None


# --- Add -------------------------------------------------------------------------------


def test_create_page_loads_with_defaults(admin_client: Client) -> None:
    CompanyFactory.create(name="Acme GmbH")
    response = admin_client.get(CREATE_URL)
    assert response.status_code == 200
    assert response.context["application_form"]["stage"].value() == stage("Applied").pk
    assertContains(response, '<option value="Acme GmbH">')  # company suggestions


# One POST creates the company, the posting and the application, with its first event.
def test_create_application(admin_client: Client) -> None:
    tag = TagFactory.create(name="remote")
    response = admin_client.post(CREATE_URL, create_data(**{"application-tags": [tag.pk]}))

    application = Application.objects.get()
    assertRedirects(response, application.get_absolute_url())
    assert application.posting.title == "Backend Developer"
    assert application.posting.company == Company.objects.get(name="Acme GmbH")
    assert application.posting.triage_status == TriageStatus.APPLIED
    assert application.applied_on == timezone.localdate()
    assert list(application.tags.all()) == [tag]
    assert application.events.get().to_stage == stage("Applied")


# Typing an existing company's name in other letter case links it (no duplicate).
def test_create_links_existing_company(admin_client: Client) -> None:
    acme = CompanyFactory.create(name="Acme GmbH")
    admin_client.post(CREATE_URL, create_data(**{"posting-company_name": "acme gmbh"}))
    assert Application.objects.get().posting.company == acme
    assert Company.objects.count() == 1


# Errors in either form: the page is shown again with the errors, and NOTHING is saved.
def test_create_with_errors_saves_nothing(admin_client: Client) -> None:
    data = create_data(**{"posting-title": "", "posting-salary_min": "70000",
                          "posting-salary_max": "50000"})  # fmt: skip
    response = admin_client.post(CREATE_URL, data)
    assert response.status_code == 200
    assertContains(response, "This field is required.")
    assertContains(response, "minimum salary")
    assert not JobPosting.objects.exists()
    assert not Company.objects.exists()


# --- Edit ------------------------------------------------------------------------------


def test_edit_page_has_no_stage_field(admin_client: Client) -> None:
    application = started()
    response = admin_client.get(reverse("applications:edit", args=[application.pk]))
    assert "stage" not in response.context["application_form"].fields
    assert response.context["posting_form"]["company_name"].value() == (
        application.posting.company_display
    )


def test_edit_saves_both_forms(admin_client: Client) -> None:
    application = started()
    data = create_data(**{"posting-title": "Senior Backend Developer",
                          "application-priority": "high"})  # fmt: skip
    del data["application-stage"]
    response = admin_client.post(reverse("applications:edit", args=[application.pk]), data)
    assertRedirects(response, application.get_absolute_url())
    application.refresh_from_db()
    assert application.posting.title == "Senior Backend Developer"
    assert application.priority == "high"
    assert application.stage == stage("Applied")  # unchanged


def test_edit_with_errors_shows_form(admin_client: Client) -> None:
    application = started()
    data = create_data(**{"posting-title": ""})
    response = admin_client.post(reverse("applications:edit", args=[application.pk]), data)
    assert response.status_code == 200
    assertContains(response, "Edit application")


# --- Detail ----------------------------------------------------------------------------


def test_detail_page_shows_application_and_timeline(admin_client: Client) -> None:
    application = started(notes="Ask about the team size")
    application.posting.salary_min, application.posting.salary_max = 55_000, 70_000
    application.posting.save()
    services.add_event(application, kind=EventKind.CALL, summary="Call with HR")

    response = admin_client.get(application.get_absolute_url())
    assertContains(response, application.posting.title)
    assertContains(response, "Call with HR")
    assertContains(response, "Created in")
    assertContains(response, "55,000-70,000 EUR per year")
    assertContains(response, "Ask about the team size")
    assertContains(response, "Close application…")


def test_detail_of_closed_application_shows_outcome(admin_client: Client) -> None:
    application = started(stage=stage("Interviewing"))
    services.close_application(application, reason="salary")
    response = admin_client.get(application.get_absolute_url())
    assertContains(response, "Got as far as")
    assertContains(response, "Salary expectations")
    assertNotContains(response, "Close application…")


def test_unknown_application_is_404(admin_client: Client) -> None:
    assert admin_client.get(reverse("applications:detail", args=[999999])).status_code == 404


# --- Actions ---------------------------------------------------------------------------


def test_change_stage(admin_client: Client) -> None:
    application = started(stage=stage("Applied"))
    application.events.update(occurred_at=timezone.now() - timedelta(days=5))  # applied 5 days ago
    url = reverse("applications:change_stage", args=[application.pk])
    response = admin_client.post(
        url, {"stage": stage("Screening").pk, "occurred_at": when(2), "note": "HR call"},
        follow=True,  # follow the redirect, to see the message on the detail page
    )  # fmt: skip
    assertContains(response, "Moved to “Screening”.")
    application.refresh_from_db()
    assert application.stage == stage("Screening")
    assert application.events.get(to_stage=stage("Screening")).details == "HR call"


# Errors from the service (future date) and from the form come back as messages.
def test_change_stage_errors_are_shown(admin_client: Client) -> None:
    application = started()
    url = reverse("applications:change_stage", args=[application.pk])
    future = (timezone.localtime() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    response = admin_client.post(url, {"stage": stage("Screening").pk, "occurred_at": future},
                                 follow=True)  # fmt: skip
    assertContains(response, "can&#x27;t be in the future")
    response = admin_client.post(url, {"stage": "", "occurred_at": when()}, follow=True)
    assertContains(response, "New stage: This field is required.")


def test_actions_need_post(admin_client: Client) -> None:
    application = started()
    for name in ("change_stage", "close", "add_event", "delete"):
        url = reverse(f"applications:{name}", args=[application.pk])
        assert admin_client.get(url).status_code == 405


def test_close_with_reason(admin_client: Client) -> None:
    application = started()
    url = reverse("applications:close", args=[application.pk])
    data = {"stage": stage("Rejected").pk, "reason": "other_candidate", "details": "",
            "occurred_at": when()}  # fmt: skip
    response = admin_client.post(url, data, follow=True)
    assertContains(response, "Application closed as “Rejected”.")
    application.refresh_from_db()
    assert application.is_closed
    assert application.rejection_reason == "other_candidate"


def test_close_errors_are_shown(admin_client: Client) -> None:
    application = started()
    url = reverse("applications:close", args=[application.pk])
    data = {"stage": stage("Withdrawn").pk, "reason": "salary", "occurred_at": when()}
    assertContains(admin_client.post(url, data, follow=True), "only fits a lost")
    assertContains(admin_client.post(url, {"stage": ""}, follow=True), "required")


def test_add_event(admin_client: Client) -> None:
    application = started()
    url = reverse("applications:add_event", args=[application.pk])
    data = {"kind": "call", "summary": "Call with Jana", "occurred_at": when(1), "details": ""}
    response = admin_client.post(url, data, follow=True)
    assertContains(response, "Added to the timeline.")
    assert application.events.filter(kind=EventKind.CALL, summary="Call with Jana").exists()


def test_add_event_errors_are_shown(admin_client: Client) -> None:
    application = started()
    url = reverse("applications:add_event", args=[application.pk])
    # "stage_change" isn't offered in this form, so it's an invalid choice.
    data = {"kind": "stage_change", "summary": "", "occurred_at": when()}
    response = admin_client.post(url, data, follow=True)
    assertContains(response, "Select a valid choice")
    future = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    data = {"kind": "note", "summary": "x", "occurred_at": future}
    assertContains(admin_client.post(url, data, follow=True), "future")


# Deleting keeps the posting (now "saved") and goes back to the list.
def test_delete(admin_client: Client) -> None:
    application = started()
    posting = application.posting
    response = admin_client.post(reverse("applications:delete", args=[application.pk]),
                                 follow=True)  # fmt: skip
    assertContains(response, "deleted. The job posting was kept.")
    assert not Application.objects.exists()
    posting.refresh_from_db()
    assert posting.triage_status == TriageStatus.SAVED


# --- services used by these pages ------------------------------------------------------


def test_add_event_service_rules() -> None:
    application = started()
    with pytest.raises(services.ApplicationError, match="changing the stage"):
        services.add_event(application, kind=EventKind.STAGE_CHANGE, summary="x")
    with pytest.raises(services.ApplicationError, match="summary"):
        services.add_event(application, kind=EventKind.NOTE, summary="   ")


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (55_000, 70_000, "55,000-70,000 EUR per year"),
        (60_000, 60_000, "60,000 EUR per year"),
        (55_000, None, "from 55,000 EUR per year"),
        (None, 70_000, "up to 70,000 EUR per year"),
        (None, None, ""),
    ],
)
def test_salary_display(low: int | None, high: int | None, expected: str) -> None:
    assert JobPosting(salary_min=low, salary_max=high).salary_display == expected


def test_salary_expectation_display() -> None:
    assert Application(salary_expectation=65_000).salary_expectation_display == "65,000 EUR"
    assert Application().salary_expectation_display == ""


# save(commit=False) builds the posting (and links the company) without saving it.
def test_posting_form_save_without_commit() -> None:
    data = create_data()
    form = PostingForm(data, prefix="posting")
    assert form.is_valid(), form.errors
    posting = form.save(commit=False)
    assert posting.pk is None
    assert posting.company_name_raw == "Acme GmbH"
