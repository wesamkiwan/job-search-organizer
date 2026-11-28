"""Root URL configuration: maps URL paths to views."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("organizer.accounts.urls")),
    path("applications/", include("organizer.applications.urls")),
    path("companies/", include("organizer.companies.urls")),
    path("contacts/", include("organizer.companies.contact_urls")),
    path("documents/", include("organizer.documents.urls")),
    # Both at the root: analytics owns "/" (the dashboard), core owns /settings/ and /ui/.
    path("", include("organizer.analytics.urls")),
    path("", include("organizer.core.urls")),
]
