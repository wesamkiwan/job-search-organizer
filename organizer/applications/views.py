"""Pages for applications. Views stay thin: read the request, call selectors/services,
render a template."""

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.cache import patch_vary_headers

from .forms import ApplicationFilterForm
from .models import Application
from .selectors import application_list

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
