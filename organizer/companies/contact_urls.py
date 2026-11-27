"""URLs for contacts. They live in the companies app but get their own URL namespace
("contacts:..."), so /contacts/ highlights its own sidebar item."""

from django.urls import path

from . import views

app_name = "contacts"
urlpatterns = [
    path("", views.contact_list_view, name="list"),
    path("new/", views.contact_create, name="create"),
    path("<int:pk>/", views.contact_detail, name="detail"),
    path("<int:pk>/edit/", views.contact_edit, name="edit"),
    path("<int:pk>/delete/", views.contact_delete, name="delete"),
]
