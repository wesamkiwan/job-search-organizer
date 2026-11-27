"""Unit tests for organizer/applications/services.py: the business rules of the pipeline."""

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from organizer.applications import services
from organizer.applications.models import (
    Application,
    ApplicationEvent,
    EventKind,
    RejectionReason,
)
from organizer.applications.services import ApplicationError
from organizer.jobs.models import TriageStatus
from tests.factories import ApplicationFactory, JobPostingFactory, stage

pytestmark = pytest.mark.django_db


def new_application(**fields: Any) -> Application:
    """An unsaved application for a fresh posting (what a form's save(commit=False) gives)."""
    return ApplicationFactory.build(posting=JobPostingFactory.create(), **fields)


def days_ago(days: int) -> datetime:
    return timezone.now() - timedelta(days=days)


# --- create_application ----------------------------------------------------------------


# Without a stage it starts in "Applied", dated today, with a first timeline event, and
# the posting is marked as applied.
def test_create_defaults_to_applied_today() -> None:
    application = services.create_application(new_application(stage=None))

    assert application.pk is not None
    assert application.stage == stage("Applied")
    assert application.applied_on == timezone.localdate()
    event = application.events.get()  # .get(): exactly one event, or the test fails
    assert (event.kind, event.from_stage, event.to_stage) == (
        EventKind.STAGE_CHANGE,
        None,
        stage("Applied"),
    )
    application.posting.refresh_from_db()
    assert application.posting.triage_status == TriageStatus.APPLIED


# Only saved for later: no applied date, posting marked "saved".
def test_create_in_saved_stage() -> None:
    application = services.create_application(new_application(stage=stage("Saved")))
    assert application.applied_on is None
    assert application.posting.triage_status == TriageStatus.SAVED


# An applied date that you enter yourself is kept.
def test_create_keeps_given_applied_on() -> None:
    application = services.create_application(new_application(applied_on=date(2026, 11, 2)))
    assert application.applied_on == date(2026, 11, 2)


# Logging an old application that was already rejected: it's closed right away.
def test_create_directly_in_final_stage() -> None:
    application = services.create_application(
        new_application(stage=stage("Rejected")), occurred_at=days_ago(10)
    )
    assert application.is_closed
    assert application.closed_at == application.events.get().occurred_at


def test_create_refuses_second_application_for_posting() -> None:
    existing = ApplicationFactory.create()
    duplicate = ApplicationFactory.build(posting=existing.posting)
    with pytest.raises(ApplicationError, match="already has an application"):
        services.create_application(duplicate)


def test_create_refuses_saved_application() -> None:
    with pytest.raises(ApplicationError, match="already saved"):
        services.create_application(ApplicationFactory.create())


# --- change_stage ----------------------------------------------------------------------


def test_change_stage_moves_and_records_event() -> None:
    application = services.create_application(new_application())
    event = services.change_stage(application, stage("Screening"), note="Call with HR")

    application.refresh_from_db()
    assert application.stage == stage("Screening")
    assert (event.from_stage, event.to_stage) == (stage("Applied"), stage("Screening"))
    assert event.summary == "Applied → Screening"
    assert event.details == "Call with HR"
    assert application.events.count() == 2


# Leaving "Saved" means you applied: applied_on is filled with the (backdated) date.
def test_leaving_saved_sets_applied_on_from_occurred_at() -> None:
    application = services.create_application(
        new_application(stage=stage("Saved")), occurred_at=days_ago(5)
    )
    when = days_ago(3)
    services.change_stage(application, stage("Applied"), occurred_at=when)
    assert application.applied_on == timezone.localdate(when)
    assert application.posting.triage_status == TriageStatus.APPLIED


def test_change_to_same_stage_is_refused() -> None:
    application = services.create_application(new_application())
    with pytest.raises(ApplicationError, match="already in"):
        services.change_stage(application, stage("Applied"))


def test_future_date_is_refused() -> None:
    application = services.create_application(new_application())
    with pytest.raises(ApplicationError, match="future"):
        services.change_stage(
            application, stage("Screening"), occurred_at=timezone.now() + timedelta(days=1)
        )


# The timeline stays in order: no stage change before the previous one.
def test_change_before_last_stage_change_is_refused() -> None:
    application = services.create_application(new_application(), occurred_at=days_ago(3))
    with pytest.raises(ApplicationError, match="before the last stage change"):
        services.change_stage(application, stage("Screening"), occurred_at=days_ago(5))


# ...but within the same minute is fine: a form's "now" (14:05) right after creating the
# application at 14:05:33 must not be refused.
def test_change_in_same_minute_is_allowed() -> None:
    application = services.create_application(new_application())
    created = application.events.get().occurred_at
    same_minute = created.replace(second=0, microsecond=0)
    services.change_stage(application, stage("Screening"), occurred_at=same_minute)


# Reaching a lost stage closes the application and remembers how far it got.
def test_lost_stage_closes_and_keeps_outcome_stage() -> None:
    application = services.create_application(
        new_application(stage=stage("Interviewing")), occurred_at=days_ago(5)
    )
    when = days_ago(1)
    services.change_stage(application, stage("Ghosted"), occurred_at=when)
    assert application.closed_at == when
    assert application.outcome_stage == stage("Interviewing")


# Rejected → Ghosted: still the stage from before the end, not "Rejected".
def test_moving_between_final_stages_keeps_outcome_stage() -> None:
    application = services.create_application(new_application(stage=stage("Interviewing")))
    services.change_stage(application, stage("Rejected"))
    services.change_stage(application, stage("Ghosted"))
    assert application.outcome_stage == stage("Interviewing")


# Reopening (the rejection was a mistake) clears all outcome fields.
def test_reopening_clears_outcome() -> None:
    application = services.create_application(new_application(stage=stage("Screening")))
    services.close_application(application, reason=RejectionReason.SALARY, details="too low")
    services.change_stage(application, stage("Interviewing"))

    application.refresh_from_db()
    assert not application.is_closed
    assert application.outcome_stage is None
    assert (application.rejection_reason, application.rejection_details) == ("", "")


# Accepting an offer closes the application, but it isn't "lost": no outcome stage.
def test_won_stage_closes_without_outcome_stage() -> None:
    application = services.create_application(new_application(stage=stage("Offer")))
    services.change_stage(application, stage("Accepted"))
    assert application.is_closed
    assert application.outcome_stage is None


# --- close_application -----------------------------------------------------------------


def test_close_defaults_to_rejected_with_reason() -> None:
    application = services.create_application(new_application())
    event = services.close_application(
        application, reason=RejectionReason.OTHER_CANDIDATE, details="Internal hire"
    )
    application.refresh_from_db()
    assert application.stage == stage("Rejected")
    assert application.rejection_reason == RejectionReason.OTHER_CANDIDATE
    assert application.rejection_details == "Internal hire"
    assert application.outcome_stage == stage("Applied")
    assert event.to_stage == stage("Rejected")


def test_withdraw() -> None:
    application = services.create_application(new_application())
    services.close_application(application, stage=stage("Withdrawn"))
    assert application.is_closed


def test_close_refuses_non_final_stage() -> None:
    application = services.create_application(new_application())
    with pytest.raises(ApplicationError, match="not a final stage"):
        services.close_application(application, stage=stage("Offer"))


def test_close_refuses_reason_for_non_lost_stage() -> None:
    application = services.create_application(new_application())
    with pytest.raises(ApplicationError, match="only fits a lost"):
        services.close_application(
            application, stage=stage("Withdrawn"), reason=RejectionReason.SALARY
        )


def test_close_refuses_already_closed() -> None:
    application = services.create_application(new_application())
    services.close_application(application)
    with pytest.raises(ApplicationError, match="already closed"):
        services.close_application(application)


# --- transactions ----------------------------------------------------------------------


# All or nothing: if writing the event fails, the stage change is rolled back too.
def test_change_stage_is_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    application = services.create_application(new_application())

    def broken_create(**kwargs: Any) -> None:
        raise RuntimeError("database hiccup")

    # monkeypatch: replace a function for this one test (restored automatically after).
    monkeypatch.setattr(ApplicationEvent.objects, "create", broken_create)
    with pytest.raises(RuntimeError):
        services.change_stage(application, stage("Screening"))

    application.refresh_from_db()  # what's REALLY in the database
    assert application.stage == stage("Applied")


# --- admin uses the services -----------------------------------------------------------


def admin_change_url(application: Application) -> str:
    return reverse("admin:applications_application_change", args=[application.pk])


def management_form(prefix: str) -> dict[str, str]:
    """The hidden counter fields Django's admin sends for each inline table."""
    return {f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"}


# Adding an application in the admin goes through create_application (first event).
def test_admin_add_writes_first_event(admin_client: Client) -> None:
    posting = JobPostingFactory.create()
    data = {
        "posting": posting.pk,
        "stage": stage("Applied").pk,
        "priority": "medium",
        "salary_expectation_currency": "EUR",
        "custom_data": "{}",
        **management_form("events"),
        **management_form("tasks"),
    }
    response = admin_client.post(reverse("admin:applications_application_add"), data)
    assert response.status_code == 302  # saved, redirected to the list
    application = Application.objects.get(posting=posting)
    assert application.events.get().to_stage == stage("Applied")


# On an existing application the stage can't be edited in the admin.
def test_admin_stage_is_read_only_on_change(admin_client: Client) -> None:
    application = services.create_application(new_application())
    response = admin_client.get(admin_change_url(application))
    assert "stage" not in response.context["adminform"].form.fields


# Editing other fields of an existing application in the admin works normally.
def test_admin_edit_saves_other_fields(admin_client: Client) -> None:
    application = services.create_application(new_application())
    event = application.events.get()
    data = {
        "posting": application.posting.pk,
        "priority": "high",
        "salary_expectation_currency": "EUR",
        "custom_data": "{}",
        # The read-only timeline table still sends its one existing row.
        "events-TOTAL_FORMS": "1",
        "events-INITIAL_FORMS": "1",
        "events-0-id": event.pk,
        "events-0-application": application.pk,
        **management_form("tasks"),
    }
    response = admin_client.post(admin_change_url(application), data)
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.priority == "high"
    assert application.stage == stage("Applied")  # unchanged
