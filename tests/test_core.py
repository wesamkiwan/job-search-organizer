from django.test import Client
from django.urls import reverse
from pytest_django import Settings
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

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
