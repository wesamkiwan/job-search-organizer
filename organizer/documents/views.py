"""Document library pages: list, add, detail (with versions), edit, delete, download."""

from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from organizer.applications.models import Application
from organizer.core.forms import form_errors_to_messages

from . import services
from .forms import DocumentFilterForm, DocumentForm, SendDocumentForm, VersionUploadForm
from .models import ApplicationDocument, Document, DocumentVersion
from .selectors import document_list, versions_of
from .services import DocumentError

# --- List ----------------------------------------------------------------------------------


def document_list_view(request: HttpRequest) -> HttpResponse:
    """All documents, with search (also inside the files) and filters. Like the company
    list, the search box uses HTMX's hx-select to swap only the results."""
    form = DocumentFilterForm(request.GET)
    context = {"documents": document_list(**form.values()), "form": form}
    return render(request, "documents/document_list.html", context)


# --- Add / edit ----------------------------------------------------------------------------


def document_create(request: HttpRequest) -> HttpResponse:
    """One page, two forms: the document and its first file (version 1).

    request.FILES holds the uploaded files. They are NOT in request.POST, and the HTML
    form must say enctype="multipart/form-data", or the browser sends no file at all.
    """
    document_form = DocumentForm(request.POST or None, prefix="document")
    upload_form = VersionUploadForm(request.POST or None, request.FILES or None, prefix="version")

    if request.method == "POST":
        # Validate both, so both show their errors (see applications.views._all_valid).
        valid = [document_form.is_valid(), upload_form.is_valid()]
        if all(valid):
            try:
                with transaction.atomic():
                    document = document_form.save()
                    services.upload_version(
                        document,
                        upload_form.cleaned_data["file"],
                        change_notes=upload_form.cleaned_data["change_notes"],
                    )
            except DocumentError as error:
                # The transaction was rolled back: no document without its file.
                upload_form.add_error("file", str(error))
            else:
                messages.success(request, f"“{document}” added.")
                return redirect(document)

    context = {"document_form": document_form, "upload_form": upload_form}
    return render(request, "documents/document_create.html", context)


def document_edit(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(Document, pk=pk)
    form = DocumentForm(request.POST or None, instance=document)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Changes saved.")
        return redirect(document)
    return render(request, "documents/document_edit.html", {"form": form, "document": document})


# --- Detail --------------------------------------------------------------------------------


def document_detail(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(Document.objects.select_related("document_type"), pk=pk)
    versions = list(versions_of(document))
    context = {
        "document": document,
        "versions": versions,
        "latest": versions[0] if versions else None,
        "upload_form": VersionUploadForm(),
        "is_sent": any(v.sent_count for v in versions),  # type: ignore[attr-defined]
    }
    return render(request, "documents/document_detail.html", context)


# The actions below only accept POST (they change data) and redirect back to a page
# (Post/Redirect/Get), with a success or error message.


@require_POST
def version_upload(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(Document, pk=pk)
    form = VersionUploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            version = services.upload_version(
                document, form.cleaned_data["file"], change_notes=form.cleaned_data["change_notes"]
            )
        except DocumentError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Version {version.version_number} uploaded.")
    else:
        form_errors_to_messages(request, form)
    return redirect(document)


@require_POST
def version_delete(request: HttpRequest, pk: int) -> HttpResponse:
    version = get_object_or_404(DocumentVersion.objects.select_related("document"), pk=pk)
    document, number = version.document, version.version_number
    try:
        services.delete_version(version)
    except DocumentError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Version {number} deleted.")
    return redirect(document)


@require_POST
def document_delete(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(Document, pk=pk)
    title = str(document)
    try:
        services.delete_document(document)
    except DocumentError as error:
        messages.error(request, str(error))
        return redirect(document)
    messages.success(request, f"“{title}” and its files deleted.")
    return redirect("documents:list")


# --- Sent with an application (the form lives on the application's page) -----------------


@require_POST
def send_document(request: HttpRequest, application_pk: int) -> HttpResponse:
    """Record that a version was sent with an application; back to the application."""
    application = get_object_or_404(Application, pk=application_pk)
    form = SendDocumentForm(request.POST, application=application)
    if form.is_valid():
        version = form.cleaned_data["version"]
        try:
            services.attach_version(application, version, sent_at=form.cleaned_data["sent_at"])
        except DocumentError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"“{version}” recorded as sent.")
    else:
        form_errors_to_messages(request, form)
    return redirect(application)


@require_POST
def remove_sent_document(request: HttpRequest, pk: int) -> HttpResponse:
    sent = get_object_or_404(
        ApplicationDocument.objects.select_related("application", "document_version__document"),
        pk=pk,
    )
    application, version = sent.application, sent.document_version
    services.detach_version(sent)
    messages.success(request, f"“{version}” is no longer recorded as sent.")
    return redirect(application)


# --- Download ------------------------------------------------------------------------------


def version_download(request: HttpRequest, pk: int) -> FileResponse:
    """Send a stored file to the browser: the ONLY way to get a document's file.

    The files are never served as public /media/ URLs. This view runs behind the login
    (LoginRequiredMiddleware), so only you can open them, and a link to a file stops
    working when you are logged out.

    ?preview=1 asks the browser to SHOW the file (PDFs and images, in a new tab) instead
    of saving it.
    """
    version = get_object_or_404(DocumentVersion, pk=pk)
    preview = request.GET.get("preview") == "1" and version.can_preview
    # FileResponse streams the file in chunks (it is never loaded into memory whole) and
    # closes it at the end. as_attachment=True → "Content-Disposition: attachment": the
    # browser saves the file, under the original name you uploaded it with.
    response = FileResponse(
        version.file.open("rb"),
        as_attachment=not preview,
        filename=version.original_filename,
        content_type=version.mime_type,
    )
    # "private": personal files must not be kept by shared caches (proxies). (Browsers
    # also get "X-Content-Type-Options: nosniff" from Django's SecurityMiddleware, so they
    # trust our content type instead of guessing one from the bytes.)
    response["Cache-Control"] = "private, no-cache"
    return response
