from django.urls import path

from . import views

app_name = "analytics"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),  # the start page
    path("dashboard/applications/", views.drilldown, name="drilldown"),
    path("dashboard/goal/", views.goal_set, name="goal_set"),
    path("dashboard/goal/<int:pk>/stop/", views.goal_stop, name="goal_stop"),
    path("dashboard/layout/", views.layout_save, name="layout_save"),
    path("dashboard/layout/show/", views.layout_show, name="layout_show"),
    path("dashboard/layout/reset/", views.layout_reset, name="layout_reset"),
    # <slug:key>: letters, digits, "-" and "_", e.g. /dashboard/export/time_in_stage.csv
    path("dashboard/export/<slug:key>.csv", views.export_csv, name="export"),
]
