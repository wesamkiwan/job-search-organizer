import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django import Settings
from pytest_django.asserts import (
    assertContains,
    assertNotContains,
    assertRedirects,
    assertTemplateUsed,
)

from organizer.core.models import UserSettings

# Every page needs login (LoginRequiredMiddleware), so these tests use pytest-django's
# admin_client fixture: a test client that is already logged in as a superuser.


# The home page (dashboard) loads and is rendered with the right template.
def test_home_page_loads(admin_client: Client) -> None:
    response = admin_client.get(reverse("core:home"))
    assert response.status_code == 200
    assertTemplateUsed(response, "core/home.html")


# The sidebar marks the current page for screen readers (and highlights it).
def test_home_marks_dashboard_as_current_page(admin_client: Client) -> None:
    response = admin_client.get(reverse("core:home"))
    assertContains(response, 'aria-current="page"')


# The UI kit is a development tool: it must not exist when DEBUG is off (production).
def test_ui_gallery_hidden_when_debug_off(admin_client: Client) -> None:
    response = admin_client.get(reverse("core:ui"))
    assert response.status_code == 404


# During development (DEBUG on) the UI kit page loads.
def test_ui_gallery_loads_when_debug_on(admin_client: Client, settings: Settings) -> None:
    settings.DEBUG = True
    response = admin_client.get(reverse("core:ui"))
    assert response.status_code == 200


# The sidebar only links to the UI kit in development, never in production.
def test_ui_kit_link_only_in_debug(admin_client: Client, settings: Settings) -> None:
    url = reverse("core:ui")
    response = admin_client.get(reverse("core:home"))
    assertNotContains(response, url)
    settings.DEBUG = True
    response = admin_client.get(reverse("core:home"))
    assertContains(response, url)


# --- Settings page ---------------------------------------------------------------------

SETTINGS_URL = reverse("core:settings")
VALID_SETTINGS = {
    "home_location": "Köln",
    "default_currency": "CHF",
    "ghosted_after_days": "21",
    "date_format": "Y-m-d",
}


# The settings page loads and is rendered with the right template.
def test_settings_page_loads(admin_client: Client) -> None:
    response = admin_client.get(SETTINGS_URL)
    assert response.status_code == 200
    assertTemplateUsed(response, "core/settings.html")


# A valid form is saved, then the browser is redirected back (Post/Redirect/Get)
# and the "Settings saved." message appears on the next page.
def test_settings_save_redirects_and_shows_message(admin_client: Client) -> None:
    # follow=True: the client follows the redirect itself, so `response` is the page we
    # land on. (A second get() would not work: a message is shown once, then deleted,
    # and assertRedirects already loads the target page once to check it.)
    response = admin_client.post(SETTINGS_URL, VALID_SETTINGS, follow=True)
    assertRedirects(response, SETTINGS_URL)
    assertContains(response, "Settings saved.")

    saved = UserSettings.load()
    assert saved.home_location == "Köln"
    assert saved.default_currency == "CHF"
    assert saved.ghosted_after_days == 21
    assert saved.date_format == "Y-m-d"


# Invalid input: the form comes back (200, no redirect) with the error, and
# nothing is saved.
def test_settings_invalid_input_shows_error(admin_client: Client) -> None:
    response = admin_client.post(SETTINGS_URL, {**VALID_SETTINGS, "ghosted_after_days": "0"})
    assert response.status_code == 200
    assertContains(response, "Ensure this value is greater than or equal to 1.")
    assert UserSettings.load().ghosted_after_days == 30  # still the default


# --- UserSettings model ----------------------------------------------------------------


# The first load() creates the settings with the defaults from the spec.
@pytest.mark.django_db
def test_user_settings_defaults() -> None:
    user_settings = UserSettings.load()
    assert user_settings.home_location == ""
    assert user_settings.default_currency == "EUR"
    assert user_settings.ghosted_after_days == 30
    assert user_settings.date_format == "d.m.Y"


# Singleton: however it is saved, there is only ever one settings row.
@pytest.mark.django_db
def test_user_settings_is_a_singleton() -> None:
    UserSettings.load()
    UserSettings.load()
    UserSettings(ghosted_after_days=14).save()  # a "new" object updates row 1
    assert UserSettings.objects.count() == 1
    assert UserSettings.load().ghosted_after_days == 14


# --- TimeStampedModel ------------------------------------------------------------------
# UserSettings is our first model built on TimeStampedModel, so we test the base class
# through it. Every later model inherits the same behaviour.


# Saving for the first time fills both timestamps (on the same save they are equal).
@pytest.mark.django_db
def test_timestamps_are_set_on_create() -> None:
    user_settings = UserSettings.load()
    assert user_settings.created_at is not None
    assert user_settings.updated_at is not None


# A later save moves updated_at forward, but created_at stays as it was.
@pytest.mark.django_db
def test_updated_at_changes_on_save_but_created_at_does_not() -> None:
    user_settings = UserSettings.load()
    created, first_update = user_settings.created_at, user_settings.updated_at

    user_settings.ghosted_after_days = 14
    user_settings.save()
    user_settings.refresh_from_db()  # read the row again from the database

    assert user_settings.created_at == created
    assert user_settings.updated_at > first_update


# --- UserSettings admin ----------------------------------------------------------------


# The settings row can't be added a second time or deleted from the admin.
def test_settings_admin_has_no_add_or_delete(admin_client: Client) -> None:
    UserSettings.load()
    response = admin_client.get(reverse("admin:core_usersettings_changelist"))
    assert response.status_code == 200
    assert not response.context["has_add_permission"]
    change_url = reverse("admin:core_usersettings_change", args=[UserSettings.SINGLETON_PK])
    assertNotContains(admin_client.get(change_url), "deletelink")


# Before the row exists, adding it is allowed.
@pytest.mark.django_db
def test_settings_admin_allows_add_when_missing(admin_client: Client) -> None:
    response = admin_client.get(reverse("admin:core_usersettings_add"))
    assert response.status_code == 200


def test_settings_str() -> None:
    assert str(UserSettings()) == "Settings"


# --- Clock in the top bar --------------------------------------------------------------


# The top bar shows today's date in the format chosen in Settings (here: ISO).
def test_top_bar_shows_current_date_in_user_format(admin_client: Client) -> None:
    user_settings = UserSettings.load()
    user_settings.date_format = "Y-m-d"
    user_settings.save()
    today = timezone.localdate()

    response = admin_client.get(reverse("core:home"))
    assertContains(response, "data-clock")
    assertContains(response, 'data-date-format="Y-m-d"')
    assertContains(response, today.strftime("%Y-%m-%d"))
