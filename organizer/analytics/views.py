"""The dashboard, its drill-down list and the goal actions."""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from organizer.core.forms import form_errors_to_messages

from .forms import DashboardFilterForm, GoalForm, describe
from .metrics import GROUPS
from .models import Goal
from .widgets import DEFAULT_LAYOUT, Links, render_data


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
        "items": render_data(DEFAULT_LAYOUT, ctx, links),
        "goal_form": GoalForm(),
        "query": _encode(form.query()),  # the filters, for the goal forms' hidden field
    }
    return render(request, "analytics/dashboard.html", context)


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
