from django.urls import path

from . import views

app_name = "analytics"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),  # the start page
    path("dashboard/applications/", views.drilldown, name="drilldown"),
    path("dashboard/goal/", views.goal_set, name="goal_set"),
    path("dashboard/goal/<int:pk>/stop/", views.goal_stop, name="goal_stop"),
]
