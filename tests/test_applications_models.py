from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from organizer.applications.models import (
    Application,
    ApplicationEvent,
    EventKind,
    PipelineStage,
    StageCategory,
    Task,
)
from tests.factories import (
    ApplicationEventFactory,
    ApplicationFactory,
    PipelineStageFactory,
    TaskFactory,
    stage,
)

pytestmark = pytest.mark.django_db


# --- PipelineStage ---------------------------------------------------------------------


# The data migration created the 9 default stages, in this order.
def test_default_stages_in_order() -> None:
    names = list(PipelineStage.objects.values_list("name", flat=True))
    assert names == [
        "Saved",
        "Applied",
        "Screening",
        "Interviewing",
        "Offer",
        "Accepted",
        "Rejected",
        "Ghosted",
        "Withdrawn",
    ]


# Every category has exactly one default stage (the services rely on that).
def test_every_category_has_one_default_stage() -> None:
    defaults = PipelineStage.objects.filter(is_default_for_category=True)
    assert sorted(defaults.values_list("category", flat=True)) == sorted(StageCategory.values)


# The partial unique constraint: a second default for the same category is refused.
def test_second_default_for_a_category_is_refused() -> None:
    with pytest.raises(IntegrityError):
        PipelineStageFactory.create(category=StageCategory.LOST, is_default_for_category=True)


# ...but any number of NON-default stages per category is fine.
def test_extra_non_default_stages_are_allowed() -> None:
    PipelineStageFactory.create(category=StageCategory.LOST)
    PipelineStageFactory.create(category=StageCategory.LOST)
    assert PipelineStage.objects.filter(category=StageCategory.LOST).count() == 4


@pytest.mark.parametrize(
    ("name", "is_final"),
    [
        ("Saved", False),
        ("Interviewing", False),
        ("Accepted", True),
        ("Ghosted", True),
        ("Withdrawn", True),
    ],
)
def test_stage_is_final(name: str, is_final: bool) -> None:
    assert stage(name).is_final is is_final
    assert str(stage(name)) == name


# A stage that applications use can't be deleted.
def test_stage_in_use_is_protected() -> None:
    application = ApplicationFactory.create()
    with pytest.raises(ProtectedError):
        application.stage.delete()


# --- Application -----------------------------------------------------------------------


def test_application_defaults_and_str() -> None:
    application = ApplicationFactory.create(posting__title="Backend Developer")
    assert str(application) == "Backend Developer"
    assert application.priority == "medium"
    assert not application.is_closed
    assert application.custom_data == {}


# OneToOne: a second application for the same posting is refused by the database.
def test_one_application_per_posting() -> None:
    application = ApplicationFactory.create()
    with pytest.raises(IntegrityError):
        Application.objects.create(posting=application.posting, stage=stage("Applied"))


# The reverse side of a OneToOne is a single object, not a list: posting.application
def test_posting_knows_its_application() -> None:
    application = ApplicationFactory.create()
    assert application.posting.application == application


# PROTECT: a posting with an application can't be deleted.
def test_posting_with_application_is_protected() -> None:
    application = ApplicationFactory.create()
    with pytest.raises(ProtectedError):
        application.posting.delete()


def test_interest_must_be_1_to_5() -> None:
    application = ApplicationFactory.create(interest=6)
    with pytest.raises(ValidationError):
        application.full_clean()


# --- ApplicationEvent ------------------------------------------------------------------


# CASCADE: deleting an application deletes its timeline.
def test_deleting_application_deletes_events() -> None:
    event = ApplicationEventFactory.create()
    event.application.delete()
    assert not ApplicationEvent.objects.filter(pk=event.pk).exists()


# A stage-change event must name the stage it went to.
def test_stage_change_event_needs_to_stage() -> None:
    application = ApplicationFactory.create()
    with pytest.raises(IntegrityError):
        ApplicationEvent.objects.create(application=application, kind=EventKind.STAGE_CHANGE)


def test_events_newest_first_and_str() -> None:
    application = ApplicationFactory.create()
    old = ApplicationEventFactory.create(
        application=application, occurred_at=timezone.now() - timedelta(days=3)
    )
    new = ApplicationEventFactory.create(application=application, summary="")
    assert list(application.events.all()) == [new, old]
    assert str(new) == "Note"  # no summary: falls back to the kind's label
    assert str(old) == old.summary


# --- Task ------------------------------------------------------------------------------


# Open tasks first, sorted by due date (no date last); done tasks at the end.
def test_task_ordering() -> None:
    done = TaskFactory.create(title="done", done_at=timezone.now())
    no_date = TaskFactory.create(title="no date")
    later = TaskFactory.create(title="later", due_on=date(2026, 12, 20))
    soon = TaskFactory.create(title="soon", due_on=date(2026, 12, 1))
    assert list(Task.objects.all()) == [soon, later, no_date, done]
    assert done.is_done and not soon.is_done
    assert str(soon) == "soon"


# --- Admin -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url_name",
    [
        "admin:applications_pipelinestage_changelist",
        "admin:applications_application_changelist",
        "admin:applications_application_add",
        "admin:applications_task_changelist",
    ],
)
def test_admin_pages_load(admin_client: Client, url_name: str) -> None:
    ApplicationEventFactory.create()
    TaskFactory.create(application=ApplicationFactory.create())
    assert admin_client.get(reverse(url_name)).status_code == 200


def test_application_admin_change_page_loads(admin_client: Client) -> None:
    application = ApplicationEventFactory.create().application
    url = reverse("admin:applications_application_change", args=[application.pk])
    assert admin_client.get(url).status_code == 200


def test_stage_admin_counts_applications(admin_client: Client) -> None:
    ApplicationFactory.create_batch(2)  # both in "Applied"
    response = admin_client.get(reverse("admin:applications_pipelinestage_changelist"))
    counts = {s.name: s._app_count for s in response.context["cl"].result_list}
    assert counts["Applied"] == 2
    assert counts["Saved"] == 0
