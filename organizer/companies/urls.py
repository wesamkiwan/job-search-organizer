from django.urls import path

from . import views

app_name = "companies"
urlpatterns = [
    path("", views.company_list_view, name="list"),
    path("new/", views.company_create, name="create"),  # "new" is a reserved slug
    # <slug:slug>: letters, digits, - and _, e.g. /companies/nordlicht-software-gmbh/
    path("<slug:slug>/", views.company_detail, name="detail"),
    path("<slug:slug>/edit/", views.company_edit, name="edit"),
    path("<slug:slug>/delete/", views.company_delete, name="delete"),
]
