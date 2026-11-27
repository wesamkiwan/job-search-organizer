from django.urls import path

from . import views

app_name = "applications"
urlpatterns = [
    path("", views.application_list_view, name="list"),
    path("new/", views.application_create, name="create"),
    # <int:pk> captures a number from the URL and passes it to the view as pk=...
    path("<int:pk>/", views.application_detail, name="detail"),
    path("<int:pk>/edit/", views.application_edit, name="edit"),
    path("<int:pk>/stage/", views.application_change_stage, name="change_stage"),
    path("<int:pk>/close/", views.application_close, name="close"),
    path("<int:pk>/events/", views.application_add_event, name="add_event"),
    path("<int:pk>/delete/", views.application_delete, name="delete"),
]
