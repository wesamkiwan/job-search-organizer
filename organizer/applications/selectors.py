"""Read queries for applications (the counterpart of services.py, which writes).

Views, the dashboard and exports reuse these, so "which applications match?" is answered
the same way everywhere, and the queries are tuned in one place (no N+1).
"""

from dataclasses import dataclass

from django.db.models import F, Func, OrderBy, Prefetch, Q, QuerySet
from django.db.models.functions import Coalesce, Lower

from organizer.jobs.models import JobPosting, RemoteType, Tag

from .models import Application, PipelineStage, Priority


class Status:
    """Which applications to show, by their state (the filter above the list)."""

    OPEN = "open"
    CLOSED = "closed"
    ARCHIVED = "archived"
    ALL = "all"

    CHOICES = (
        (OPEN, "Open"),
        (CLOSED, "Closed"),
        (ARCHIVED, "Archived"),
        (ALL, "All"),
    )


# Sort keys the user can choose (the column headers) → the database expression.
# A whitelist: a sort value from the URL is never passed to order_by() directly.
SORT_FIELDS: dict[str, F | Func] = {
    "title": Lower("posting__title"),
    "company": Coalesce(Lower("posting__company__name"), Lower("posting__company_name_raw")),
    "stage": F("stage__order"),
    "applied": F("applied_on"),
    "salary": F("salary_expectation"),
    "updated": F("updated_at"),
}
DEFAULT_SORT = "-updated"


@dataclass(frozen=True)
class ApplicationFilters:
    """Everything the list can be filtered and sorted by. All optional."""

    search: str = ""
    stage: PipelineStage | None = None
    status: str = Status.OPEN
    priority: str = ""
    city: str = ""
    remote_type: str = ""
    sort: str = DEFAULT_SORT


def application_list(filters: ApplicationFilters | None = None) -> QuerySet[Application]:
    """Applications matching the filters, with everything a list row shows preloaded."""
    filters = filters or ApplicationFilters()

    applications = Application.objects.select_related(
        # One JOIN query instead of one extra query per row for each of these.
        "posting__company",
        "posting__source",
        "stage",
    ).prefetch_related(
        # Tags are many-to-many: a 2nd query loads the tags of ALL rows at once.
        Prefetch("tags", queryset=Tag.objects.order_by("name"))
    )

    if filters.search:
        term = filters.search.strip()
        applications = applications.filter(
            Q(posting__title__icontains=term)
            | Q(posting__company__name__icontains=term)
            | Q(posting__company_name_raw__icontains=term)
            | Q(posting__city__icontains=term)
            | Q(notes__icontains=term)
        )
    if filters.stage is not None:
        applications = applications.filter(stage=filters.stage)
    if filters.priority in Priority.values:
        applications = applications.filter(priority=filters.priority)
    if filters.city:
        # iexact: "berlin" matches "Berlin" (exact match, ignoring upper/lower case).
        applications = applications.filter(posting__city__iexact=filters.city)
    if filters.remote_type in RemoteType.values:
        applications = applications.filter(posting__remote_type=filters.remote_type)
    applications = _filter_status(applications, filters.status)

    return applications.order_by(*_ordering(filters.sort))


def application_cities() -> list[str]:
    """The cities of postings that have an application, A to Z (for the Location filter).

    distinct(): every city once. The list grows by itself when you apply in a new city.
    """
    cities = (
        JobPosting.objects.filter(application__isnull=False)
        .exclude(city="")
        .order_by("city")
        .values_list("city", flat=True)  # just the values, not whole objects
        .distinct()
    )
    return list(cities)


def _filter_status(applications: QuerySet[Application], status: str) -> QuerySet[Application]:
    if status == Status.ALL:
        return applications
    if status == Status.ARCHIVED:
        return applications.filter(is_archived=True)
    applications = applications.filter(is_archived=False)
    if status == Status.CLOSED:
        return applications.filter(closed_at__isnull=False)
    return applications.filter(closed_at__isnull=True)  # OPEN, and anything unknown


def _ordering(sort: str) -> tuple[OrderBy, str]:
    """Sort key → ORDER BY. A leading "-" means descending. Empty values always come last."""
    descending = sort.startswith("-")
    expression = SORT_FIELDS.get(sort.removeprefix("-"))
    if expression is None:  # unknown value from the URL: fall back to the default
        return _ordering(DEFAULT_SORT)
    order = expression.desc(nulls_last=True) if descending else expression.asc(nulls_last=True)
    # "-pk" as a tie-breaker: rows with equal values keep a stable order between pages.
    return order, "-pk"
