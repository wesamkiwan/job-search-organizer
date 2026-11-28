"""The dashboard, its drill-down list, the goal and layout actions, and the CSV export."""

import csv
import json

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from organizer.core.forms import form_errors_to_messages

from . import cache, layout
from .filters import FilterContext
from .forms import DashboardFilterForm, GoalForm, describe
from .metrics import GROUPS
from .models import Goal
from .widgets import WIDGETS, Links


def dashboard(request: HttpRequest) -> HttpResponse:
    """The start page. The filter bar re-requests this page with HTMX; hx-select swaps
    only #dashboard-content (like the company search), so no separate partial is needed."""
    form = DashboardFilterForm(request.GET)
    ctx = form.context()
    links = Links(form.query())
    previous = ctx.previous()
    context = {
        "form": form,
        "ctx": ctx,
        "period_text": describe(ctx.period),
        "previous_text": describe(previous.period) if previous else "",
        "items": _items(ctx, links),
        "hidden": [WIDGETS[key] for key in layout.hidden_widgets()],
        "goal_form": GoalForm(),
        "query": _encode(form.query()),  # the filters, for the goal forms' hidden field
    }
    return render(request, "analytics/dashboard.html", context)


def _items(ctx: FilterContext, links: Links) -> list[dict[str, object]]:
    """The widgets of the saved layout, each with its (cached) data and its size."""
    return [
        {"widget": WIDGETS[p.key], "size": p.size, **cache.build(WIDGETS[p.key], ctx, links)}
        for p in layout.placements()
    ]


def drilldown(request: HttpRequest) -> HttpResponse:
    """The applications behind a number or a chart bar, e.g. "got a response, last 30
    days". Uses the same group functions as the metrics, so the list always matches."""
    group = GROUPS.get(request.GET.get("group", ""))
    if group is None:
        raise Http404("Unknown group.")
    form = DashboardFilterForm(request.GET)
    ctx = form.context()
    applications = (
        group.members(ctx)
        .select_related("posting__company", "stage")
        .order_by("-applied_on", "-pk")
    )
    page = Paginator(applications, 50).get_page(request.GET.get("page"))
    back = reverse("analytics:dashboard")
    query = form.query()
    context = {
        "group": group,
        "page": page,
        "period_text": describe(ctx.period),
        "back_url": f"{back}?{_encode(query)}" if query else back,
        "query": _encode({**query, "group": group.key}),
    }
    return render(request, "analytics/drilldown.html", context)


@require_POST
def goal_set(request: HttpRequest) -> HttpResponse:
    """Set the weekly or monthly goal. The old goal is kept, inactive, as history."""
    form = GoalForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            goal = form.save(commit=False)
            Goal.objects.filter(metric=goal.metric, period=goal.period, is_active=True).update(
                is_active=False
            )
            goal.save()
        messages.success(request, f"Goal set: {goal}.")
    else:
        form_errors_to_messages(request, form)
    return _back_to_dashboard(request)


@require_POST
def goal_stop(request: HttpRequest, pk: int) -> HttpResponse:
    goal = get_object_or_404(Goal, pk=pk, is_active=True)
    goal.is_active = False
    goal.save(update_fields=("is_active", "updated_at"))
    messages.success(request, "Goal removed.")
    return _back_to_dashboard(request)


# --- layout ----------------------------------------------------------------------------------


@require_POST
def layout_save(request: HttpRequest) -> JsonResponse:
    """Save order and sizes after a drag, resize or remove (static/js/dashboard.js).

    The browser sends JSON: {"widgets": [{"key": "kpis", "size": "full"}, ...]}.
    """
    try:
        payload = json.loads(request.body or b"{}")
        layout.save(payload.get("widgets") if isinstance(payload, dict) else None)
    except (json.JSONDecodeError, layout.LayoutError) as error:
        return JsonResponse({"error": str(error)}, status=400)
    return JsonResponse({"message": "Layout saved."})


@require_POST
def layout_show(request: HttpRequest) -> HttpResponse:
    try:
        layout.show(request.POST.get("key", ""))
    except layout.LayoutError as error:
        messages.error(request, str(error))
    return _back_to_dashboard(request)


@require_POST
def layout_reset(request: HttpRequest) -> HttpResponse:
    layout.reset()
    messages.success(request, "The dashboard is back to its default layout.")
    return _back_to_dashboard(request)


# --- CSV export ------------------------------------------------------------------------------


def safe_cell(value: str) -> str:
    """Protect against "CSV injection": a cell starting with =, +, -, @ is run as a
    formula by Excel or LibreOffice when the file is opened. A leading apostrophe makes
    it plain text. (A job title from a website could start with "=HYPERLINK(...)".)"""
    return f"'{value}" if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def export_csv(request: HttpRequest, key: str) -> HttpResponse:
    """A widget's table as a CSV file, for the current filters."""
    widget = WIDGETS.get(key)
    if widget is None:
        raise Http404("Unknown widget.")
    form = DashboardFilterForm(request.GET)
    ctx = form.context()
    table = cache.build(widget, ctx, Links(form.query()))["table"]
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"dashboard-{key}-{ctx.period.end:%Y-%m-%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    # The "byte order mark" tells Excel that the file is UTF-8 (umlauts, the en dash).
    response.write("\ufeff")
    # Semicolons: what Excel expects in German (and many European) settings; with commas
    # a German Excel puts every line into a single column.
    writer = csv.writer(response, delimiter=";")
    writer.writerow(table.headers)
    for row in table.rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return response


def _encode(query: dict[str, str]) -> str:
    params = QueryDict(mutable=True)
    params.update(query)
    return params.urlencode()


def _back_to_dashboard(request: HttpRequest) -> HttpResponse:
    # The filters come back from a hidden field. Re-parsing them through the filter form
    # keeps only known, valid values (nothing else can be smuggled into the redirect).
    form = DashboardFilterForm(QueryDict(request.POST.get("query", "")))
    query = form.query()
    url = reverse("analytics:dashboard")
    return redirect(f"{url}?{_encode(query)}" if query else url)
