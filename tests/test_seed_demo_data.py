"""The seed_demo_data management command."""

import pytest
from django.core.management import CommandError, call_command
from pytest_django import Settings

from organizer.applications.models import Application, ApplicationEvent
from organizer.companies.models import Company
from organizer.jobs.models import JobPosting
from tests.factories import ApplicationFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def debug_on(settings: Settings) -> None:
    """The command only runs in development (DEBUG on). autouse: every test gets it."""
    settings.DEBUG = True


def test_creates_demo_data_through_the_services() -> None:
    call_command("seed_demo_data")  # runs a management command from Python

    demo_apps = Application.objects.filter(custom_data__demo=True)
    assert demo_apps.count() == 20
    # Every application has a timeline (written by the services), and some are closed:
    # 4 rejected + 2 ghosted + 1 withdrawn + 1 accepted.
    assert not demo_apps.filter(events__isnull=True).exists()
    assert demo_apps.filter(closed_at__isnull=False).count() == 8
    assert JobPosting.objects.filter(custom_data__demo=True, application__isnull=True).count() == 2
    # Backdated: the oldest event is weeks ago, not today.
    oldest = ApplicationEvent.objects.order_by("occurred_at").first()
    assert oldest is not None
    assert (demo_apps.first().updated_at - oldest.occurred_at).days > 7  # type: ignore[union-attr]


def test_refuses_to_run_twice() -> None:
    call_command("seed_demo_data")
    with pytest.raises(CommandError, match="already exists"):
        call_command("seed_demo_data")


# --reset removes ONLY demo rows; the user's own data stays.
def test_reset_keeps_own_data() -> None:
    own = ApplicationFactory.create()
    call_command("seed_demo_data")
    call_command("seed_demo_data", "--reset")

    assert Application.objects.filter(custom_data__demo=True).count() == 20  # recreated
    assert Application.objects.filter(pk=own.pk).exists()
    assert Company.objects.filter(custom_data__demo=True).count() == 10


def test_refuses_in_production(settings: Settings) -> None:
    settings.DEBUG = False
    with pytest.raises(CommandError, match="local development only"):
        call_command("seed_demo_data")
    call_command("seed_demo_data", "--force")  # possible, but only on purpose
    assert Application.objects.count() == 20
