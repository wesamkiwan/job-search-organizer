from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("ui/", views.ui_gallery, name="ui"),
]
