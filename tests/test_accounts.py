import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects

from organizer.accounts.models import User
from tests.factories import DEFAULT_PASSWORD, UserFactory

# Fixtures used here (all from pytest-django):
#   client:            a test browser that is NOT logged in
#   admin_client:      a test browser already logged in as a superuser
#   admin_user:        that superuser (username "admin")

LOGIN_URL = reverse("accounts:login")
LOGOUT_URL = reverse("accounts:logout")
HOME_URL = reverse("core:home")
PASSWORD = DEFAULT_PASSWORD


@pytest.fixture
def user(db: None) -> User:
    """A normal (non-admin) user with a known password.

    Requesting the `db` fixture gives this fixture database access.
    """
    return UserFactory.create(username="maria")


# --- Login page ------------------------------------------------------------------------


# The login page must be public, otherwise nobody could ever log in.
@pytest.mark.django_db
def test_login_page_is_public(client: Client) -> None:
    response = client.get(LOGIN_URL)
    assert response.status_code == 200


# Every other page needs login: anonymous visitors are sent to the login page, and
# ?next= remembers where they wanted to go.
@pytest.mark.django_db
def test_anonymous_user_is_redirected_to_login(client: Client) -> None:
    response = client.get(HOME_URL)
    assertRedirects(response, f"{LOGIN_URL}?next={HOME_URL}")


# Correct username and password: logged in and sent to the dashboard.
def test_login_with_correct_password(client: Client, user: User) -> None:
    response = client.post(LOGIN_URL, {"username": "maria", "password": PASSWORD})
    assertRedirects(response, HOME_URL)
    assert response.wsgi_request.user == user


# After logging in, the user lands on the page they originally wanted (?next=).
def test_login_redirects_to_next(client: Client, user: User) -> None:
    settings_url = reverse("core:settings")
    response = client.post(
        LOGIN_URL, {"username": "maria", "password": PASSWORD, "next": settings_url}
    )
    assertRedirects(response, settings_url)


# Wrong password: the form is shown again (200, not a redirect) with an error,
# and the user is not logged in.
def test_login_with_wrong_password_shows_error(client: Client, user: User) -> None:
    response = client.post(LOGIN_URL, {"username": "maria", "password": "wrong"})
    assert response.status_code == 200
    assertContains(response, "Please enter a correct username and password")
    assert not response.wsgi_request.user.is_authenticated


# Someone already logged in who opens the login page is sent to the dashboard
# (redirect_authenticated_user=True).
def test_logged_in_user_skips_login_page(admin_client: Client) -> None:
    response = admin_client.get(LOGIN_URL)
    assertRedirects(response, HOME_URL)


# --- Logout ----------------------------------------------------------------------------


# Logout with POST (the sidebar button) logs out and goes to the login page.
# Afterwards, pages need login again.
def test_logout_with_post(admin_client: Client) -> None:
    response = admin_client.post(LOGOUT_URL)
    assertRedirects(response, LOGIN_URL)
    response = admin_client.get(HOME_URL)
    assertRedirects(response, f"{LOGIN_URL}?next={HOME_URL}")


# Logout with GET is refused (405 Method Not Allowed), so another website can't log
# you out with a simple link or image (CSRF). The user stays logged in.
def test_logout_with_get_is_not_allowed(admin_client: Client) -> None:
    response = admin_client.get(LOGOUT_URL)
    assert response.status_code == 405
    assert admin_client.get(HOME_URL).status_code == 200


# --- Sidebar ---------------------------------------------------------------------------


# The sidebar shows who is logged in and has the sign-out form.
def test_sidebar_shows_user_and_logout(admin_client: Client, admin_user: User) -> None:
    response = admin_client.get(HOME_URL)
    assertContains(response, admin_user.get_username())
    assertContains(response, f'action="{LOGOUT_URL}"')
