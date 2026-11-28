from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("settings/", views.user_settings, name="settings"),
    path("ui/", views.ui_gallery, name="ui"),
]
