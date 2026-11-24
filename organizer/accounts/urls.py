"""Login and logout, using Django's built-in authentication views."""

from django.contrib.auth import views as auth_views
from django.urls import path

app_name = "accounts"
urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            redirect_authenticated_user=True,  # already logged in -> skip the form
        ),
        name="login",
    ),
    # Logout only accepts POST (a form button), so another site can't log you out with a link.
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
