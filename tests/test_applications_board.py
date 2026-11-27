"""The kanban board: the selector, the page and the move endpoint used by drag & drop."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from organizer.applications import services
from organizer.applications.models import Application
from organizer.applications.selectors import board_columns
from organizer.core.models import UserSettings
from tests.factories import ApplicationFactory, JobPostingFactory, stage

pytestmark = pytest.mark.django_db

BOARD_URL = reverse("applications:board")


def started(**fields: object) -> Application:
    application = ApplicationFactory.build(posting=JobPostingFactory.create(), **fields)
    return services.create_application(application)


def move_url(application: Application) -> str:
    return reverse("applications:move", args=[application.pk])


# --- selector --------------------------------------------------------------------------


def test_one_column_per_stage_in_order() -> None:
    names = [column.stage.name for column in board_columns()]
    assert names[:3] == ["Saved", "Applied", "Screening"]
    assert len(names) == 9


def test_cards_are_in_their_stage_column() -> None:
    applied = ApplicationFactory.create(stage=stage("Applied"))
    screening = ApplicationFactory.create(stage=stage("Screening"))
    columns = {column.stage.name: column.applications for column in board_columns()}
    assert columns["Applied"] == [applied]
    assert columns["Screening"] == [screening]
    assert columns["Offer"] == []


# Archived and long-closed applications are not on the board; recently closed ones are.
def test_board_hides_archived_and_old_closed() -> None:
    ApplicationFactory.create(posting__title="archived", is_archived=True)
    ApplicationFactory.create(
        posting__title="old", stage=stage("Rejected"),
        closed_at=timezone.now() - timedelta(days=45),
    )  # fmt: skip
    ApplicationFactory.create(
        posting__title="recent", stage=stage("Rejected"),
        closed_at=timezone.now() - timedelta(days=3),
    )  # fmt: skip
    shown = [a.posting.title for column in board_columns() for a in column.applications]
    assert shown == ["recent"]


# --- page ------------------------------------------------------------------------------


def test_board_page(admin_client: Client) -> None:
    ApplicationFactory.create(posting__title="Backend Developer", priority="high")
    response = admin_client.get(BOARD_URL)
    assertContains(response, "Backend Developer")
    assertContains(response, "data-move-url")
    assertContains(response, "sortablejs/sortable.min.js")  # the board's own scripts
    assertContains(response, 'aria-current="page"')  # "Board" in the view switch
    assertContains(response, "High")  # the priority badge


# The list page doesn't load the board's scripts (only pages that need them do).
def test_list_page_does_not_load_board_scripts(admin_client: Client) -> None:
    assertNotContains(admin_client.get(reverse("applications:list")), "sortable.min.js")


# Two queries for the board itself, however many cards there are.
def test_board_query_count_does_not_grow(admin_client: Client) -> None:
    UserSettings.load()

    def count() -> int:
        with CaptureQueriesContext(connection) as captured:
            admin_client.get(BOARD_URL)
        return len(captured.captured_queries)

    ApplicationFactory.create_batch(2)
    few = count()
    ApplicationFactory.create_batch(10, stage=stage("Screening"))
    assert count() == few


# --- move endpoint ---------------------------------------------------------------------


# A drop goes through change_stage: the stage changes and the timeline gets an event.
def test_move_changes_stage(admin_client: Client) -> None:
    application = started()
    response = admin_client.post(move_url(application), {"stage": stage("Screening").pk})
    assert response.status_code == 200
    assert "moved to “Screening”" in response.json()["message"]
    application.refresh_from_db()
    assert application.stage == stage("Screening")
    assert application.events.filter(to_stage=stage("Screening")).exists()


# Dropping into a final column closes the application.
def test_move_to_final_stage_closes(admin_client: Client) -> None:
    application = started()
    admin_client.post(move_url(application), {"stage": stage("Ghosted").pk})
    application.refresh_from_db()
    assert application.is_closed


# Errors come back as JSON with status 400, so board.js can put the card back.
@pytest.mark.parametrize("stage_value", ["", "abc", "999999"])
def test_move_with_bad_stage(admin_client: Client, stage_value: str) -> None:
    application = started()
    response = admin_client.post(move_url(application), {"stage": stage_value})
    assert response.status_code == 400
    assert response.json() == {"error": "Unknown stage."}


def test_move_rule_errors_are_json(admin_client: Client) -> None:
    application = started()
    response = admin_client.post(move_url(application), {"stage": stage("Applied").pk})
    assert response.status_code == 400
    assert "already in" in response.json()["error"]


def test_move_needs_post_and_login(admin_client: Client, client: Client) -> None:
    application = started()
    assert admin_client.get(move_url(application)).status_code == 405
    response = client.post(move_url(application), {"stage": stage("Screening").pk})
    assert response.status_code == 302  # not logged in → sent to the login page
