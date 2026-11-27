from django.urls import path

from . import views

app_name = "documents"
urlpatterns = [
    path("", views.document_list_view, name="list"),
    path("new/", views.document_create, name="create"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("<int:pk>/edit/", views.document_edit, name="edit"),
    path("<int:pk>/delete/", views.document_delete, name="delete"),
    path("<int:pk>/versions/", views.version_upload, name="upload_version"),
    path("versions/<int:pk>/download/", views.version_download, name="download"),
    path("versions/<int:pk>/delete/", views.version_delete, name="delete_version"),
    # Sent with an application (the forms are on the application's detail page).
    path("sent/new/<int:application_pk>/", views.send_document, name="send"),
    path("sent/<int:pk>/remove/", views.remove_sent_document, name="remove_sent"),
]
