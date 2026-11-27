"""Pages for applications. Views stay thin: read the request, call forms, selectors and
services, then render a template or redirect."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import QuerySet
from django.forms import BaseForm
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_POST

from . import services
from .forms import (
    ApplicationFilterForm,
    ApplicationForm,
    CloseForm,
    EventForm,
    PostingForm,
    StageChangeForm,
    company_names,
)
from .models import Application, PipelineStage
from .selectors import BOARD_CLOSED_DAYS, application_list, board_columns
from .services import ApplicationError

PAGE_SIZE = 25


def is_htmx(request: HttpRequest) -> bool:
    """True when HTMX sent the request (it adds the header HX-Request: true)."""
    return request.headers.get("HX-Request") == "true"


def application_list_view(request: HttpRequest) -> HttpResponse:
    """The list of applications with search, filters, sorting and pages.

    Normal request → the whole page. HTMX request (typing in the search box, changing a
    filter, clicking a column header) → only the results part, which HTMX swaps in.
    """
    form = ApplicationFilterForm(request.GET)
    filters = form.filters()
    # Paginator splits the results into pages; get_page() copes with ?page=abc or 999.
    page = Paginator(application_list(filters), PAGE_SIZE).get_page(request.GET.get("page"))

    context = {
        "form": form,
        "filters": filters,
        "page": page,
        "has_any_application": Application.objects.exists(),
    }
    template = (
        "applications/partials/application_results.html"
        if is_htmx(request)
        else "applications/application_list.html"
    )
    response = render(request, template, context)
    # The same URL returns a full page OR a fragment, depending on that header. "Vary"
    # tells browsers and caches to keep them apart (otherwise the Back button could show
    # a bare fragment).
    patch_vary_headers(response, ("HX-Request",))
    return response


# --- Kanban board ------------------------------------------------------------------------


def application_board(request: HttpRequest) -> HttpResponse:
    """The kanban board: one column per stage. Dragging a card calls application_move."""
    context = {"columns": board_columns(), "closed_days": BOARD_CLOSED_DAYS}
    return render(request, "applications/application_board.html", context)


@require_POST
def application_move(request: HttpRequest, pk: int) -> JsonResponse:
    """Move a card to another column (called by static/js/board.js after a drop).

    Answers with JSON instead of a page: the browser only needs to know "OK" (and the
    message to show) or the error, so it can put the card back.
    """
    application = get_object_or_404(_applications(), pk=pk)
    try:
        stage = PipelineStage.objects.get(pk=request.POST.get("stage", ""))
    except (PipelineStage.DoesNotExist, ValueError):  # missing, unknown or not a number
        return JsonResponse({"error": "Unknown stage."}, status=400)
    try:
        services.change_stage(application, stage)
    except ApplicationError as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse({"message": f"“{application.posting.title}” moved to “{stage}”."})


# --- Add / edit ----------------------------------------------------------------------------


def application_create(request: HttpRequest) -> HttpResponse:
    """One page, two forms: the job (JobPosting) and the application.

    prefix= keeps their fields apart in the HTML ("posting-title", "application-notes").
    Both are validated; only if BOTH are valid is anything saved, in one transaction.
    """
    # ?company=<name> (from a company page's "Add application" button) pre-fills the company.
    initial = {"company_name": request.GET.get("company", "")}
    posting_form = PostingForm(request.POST or None, prefix="posting", initial=initial)
    application_form = ApplicationForm(request.POST or None, prefix="application")

    if request.method == "POST" and _all_valid(posting_form, application_form):
        with transaction.atomic():
            posting = posting_form.save()
            # commit=False: build the object but don't save yet; the service saves it.
            application = application_form.save(commit=False)
            application.posting = posting
            services.create_application(application)
            application_form.save_m2m()  # tags can only be saved once the row exists
        messages.success(request, f"Application for “{posting.title}” added.")
        return redirect(application)  # redirect() calls application.get_absolute_url()

    return _render_form(request, posting_form, application_form, application=None)


def application_edit(request: HttpRequest, pk: int) -> HttpResponse:
    application = get_object_or_404(_applications(), pk=pk)
    posting_form = PostingForm(request.POST or None, instance=application.posting, prefix="posting")
    application_form = ApplicationForm(
        request.POST or None, instance=application, prefix="application"
    )

    if request.method == "POST" and _all_valid(posting_form, application_form):
        with transaction.atomic():
            posting_form.save()
            application_form.save()
        messages.success(request, "Changes saved.")
        return redirect(application)

    return _render_form(request, posting_form, application_form, application=application)


def _all_valid(*forms: BaseForm) -> bool:
    # Validate EVERY form first, then combine. `a.is_valid() and b.is_valid()` (or all()
    # over a generator) would stop at the first invalid form, and the second one would
    # never show its errors.
    results = [form.is_valid() for form in forms]
    return all(results)


def _render_form(
    request: HttpRequest,
    posting_form: PostingForm,
    application_form: ApplicationForm,
    application: Application | None,
) -> HttpResponse:
    context = {
        "posting_form": posting_form,
        "application_form": application_form,
        "application": application,
        "company_names": company_names(),
    }
    return render(request, "applications/application_form.html", context)


# --- Detail page ---------------------------------------------------------------------------


def application_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """Everything about one application: details, timeline, and the actions."""
    application = get_object_or_404(_applications(), pk=pk)
    context = {
        "application": application,
        "posting": application.posting,
        "events": application.events.select_related("from_stage", "to_stage"),
        "tasks": application.tasks.all(),
        "stage_form": StageChangeForm(application=application),
        "close_form": CloseForm(),
        "event_form": EventForm(),
    }
    return render(request, "applications/application_detail.html", context)


def _applications() -> QuerySet[Application]:
    """Applications with what the detail and edit pages show, loaded in one query."""
    return Application.objects.select_related(
        "posting__company", "posting__source", "stage", "outcome_stage", "referred_by"
    )


# The actions below only accept POST (they change data): @require_POST answers anything
# else with "405 Method Not Allowed". After the action they redirect back to the detail
# page (Post/Redirect/Get), with a success or error message.


@require_POST
def application_change_stage(request: HttpRequest, pk: int) -> HttpResponse:
    application = get_object_or_404(_applications(), pk=pk)
    form = StageChangeForm(request.POST, application=application)
    if form.is_valid():
        data = form.cleaned_data
        try:
            services.change_stage(
                application, data["stage"], occurred_at=data["occurred_at"], note=data["note"]
            )
        except ApplicationError as error:
            messages.error(request, str(error))
        else:  # runs only if there was no exception
            messages.success(request, f"Moved to “{data['stage']}”.")
    else:
        _form_errors_to_messages(request, form)
    return redirect(application)


@require_POST
def application_close(request: HttpRequest, pk: int) -> HttpResponse:
    application = get_object_or_404(_applications(), pk=pk)
    form = CloseForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        try:
            services.close_application(
                application,
                stage=data["stage"],
                reason=data["reason"],
                details=data["details"],
                occurred_at=data["occurred_at"],
            )
        except ApplicationError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Application closed as “{data['stage']}”.")
    else:
        _form_errors_to_messages(request, form)
    return redirect(application)


@require_POST
def application_add_event(request: HttpRequest, pk: int) -> HttpResponse:
    application = get_object_or_404(Application, pk=pk)
    form = EventForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        try:
            services.add_event(
                application,
                kind=data["kind"],
                summary=data["summary"],
                details=data["details"],
                occurred_at=data["occurred_at"],
            )
        except ApplicationError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Added to the timeline.")
    else:
        _form_errors_to_messages(request, form)
    return redirect(application)


@require_POST
def application_delete(request: HttpRequest, pk: int) -> HttpResponse:
    application = get_object_or_404(_applications(), pk=pk)
    title = application.posting.title
    services.delete_application(application)
    messages.success(request, f"Application for “{title}” deleted. The job posting was kept.")
    return redirect("applications:list")


def _form_errors_to_messages(request: HttpRequest, form: BaseForm) -> None:
    """Show a small action form's errors as messages (the form lives in a card or dialog)."""
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else ""
        for error in errors:
            messages.error(request, f"{label}: {error}" if label else str(error))
