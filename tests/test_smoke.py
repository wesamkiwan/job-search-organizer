from django.test import Client
from pytest_django import Settings
from pytest_django.asserts import assertRedirects


# Test that the test settings are being used when running tests.
def test_uses_test_settings(settings: Settings) -> None:
    assert settings.DEBUG is False
    assert "MD5" in settings.PASSWORD_HASHERS[0]


# Test that admin login page loads correctly.
def test_admin_login_page_loads(client: Client) -> None:
    response = client.get("/admin/login/")
    assert response.status_code == 200


# a visitor who isn't logged in gets redirected away from the admin to the login page.
def test_admin_requires_login(client: Client) -> None:
    response = client.get("/admin/")
    assertRedirects(response, "/admin/login/?next=/admin/")
