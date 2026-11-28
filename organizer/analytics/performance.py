"""Widgets that answer "what works?" (Phase 3, batch C).

All of them look at the applications SENT in the period (the same group as the rates):
which sources, channels, document versions and job profiles bring answers and
interviews, where applications fail and stall, when you are active, and how salaries
compare. Registered with @widget, like the core widgets; imported in AppConfig.ready().
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import mean, median
from typing import Any

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from organizer.applications.models import (
    FINAL_CATEGORIES,
    Application,
    ApplicationEvent,
    Channel,
    EventKind,
    PipelineStage,
    RejectionReason,
)
from organizer.core.models import UserSettings
from organizer.documents.models import ApplicationDocument
from organizer.jobs.models import EmploymentType, RemoteType, SalaryPeriod, Seniority
from organizer.sources.models import Source

from . import metrics
from .filters import FilterContext
from .widgets import Bar, Links, Table, bars, percent, weeks_of, widget

# Rates from fewer applications than this are shown, but marked as "few data", and the
# insights panel ignores them: 1 answer out of 2 is not a "50% response rate".
MIN_SAMPLE = 5


@dataclass(frozen=True)
class Row:
    """One line of a performance table: a group and how its applications did."""

    label: str
    sent: int
    responded: int
    interviewed: int
    url: str = ""

    @property
    def response_rate(self) -> float | None:
        return self.responded / self.sent if self.sent else None

    @property
    def interview_rate(self) -> float | None:
        return self.interviewed / self.sent if self.sent else None

    @property
    def few(self) -> bool:
        return self.sent < MIN_SAMPLE

    def table_row(self) -> tuple[str, ...]:
        return (
            self.label,
            str(self.sent),
            percent(self.response_rate),
            percent(self.interview_rate),
        )


ROW_HEADERS = ("Group", "Sent", "Response rate", "Interview rate")


def rows_by(
    ctx: FilterContext,
    field: str,
    labels: dict[Any, str],
    *,
    link_param: str = "",
    links: Links | None = None,
) -> list[Row]:
    """Sent applications grouped by one field, with their answers and interviews.

    Count(..., filter=Q(pk__in=<subquery>)) counts, per group, only the applications that
    are also in the "responded" (or "interviewed") group: one query for the whole table.
    """
    sent = ctx.sent()
    grouped = (
        sent.values(field)
        .annotate(
            n=Count("pk"),
            responded=Count("pk", filter=Q(pk__in=metrics.responded(ctx).values("pk"))),
            interviewed=Count("pk", filter=Q(pk__in=metrics.interviewed(ctx).values("pk"))),
        )
        .order_by("-n")
    )
    rows = []
    for values in grouped:
        key = values[field]
        url = ""
        if links is not None and link_param and key not in (None, ""):
            url = links.group("sent", **{link_param: str(key)})
        label = labels.get(key) or labels.get("", "Not set")
        rows.append(Row(label, values["n"], values["responded"], values["interviewed"], url))
    return rows


def _performance(rows: list[Row], empty: str) -> dict[str, Any]:
    return {
        "sections": [{"title": "", "rows": rows}] if rows else [],
        "empty_text": empty,
        "min_sample": MIN_SAMPLE,
        "table": Table(ROW_HEADERS, [row.table_row() for row in rows]),
    }


# --- by source / channel -------------------------------------------------------------------


@widget(
    "sources",
    "Performance by source",
    "Where you found the job: which sources bring answers and interviews?",
    "performance.html",
)
def sources(ctx: FilterContext, links: Links) -> dict[str, Any]:
    labels: dict[Any, str] = dict(Source.objects.values_list("pk", "name"))
    rows = rows_by(ctx, "posting__source", labels, link_param="source", links=links)
    return _performance(rows, "No applications sent in this period.")


@widget(
    "channels",
    "Performance by channel",
    "How you applied: portal, email, referral, recruiter ...",
    "performance.html",
)
def channels(ctx: FilterContext, links: Links) -> dict[str, Any]:
    labels: dict[Any, str] = {**dict(Channel.choices), "": "Not set"}
    rows = rows_by(ctx, "channel", labels, link_param="channel", links=links)
    return _performance(rows, "No applications sent in this period.")


# --- by document version (A/B comparison) ----------------------------------------------------


def document_rows(ctx: FilterContext) -> list[Row]:
    """Per document version: the sent applications it went with, and how they did."""
    sent_ids = ctx.sent().values("pk")
    responded = set(metrics.responded(ctx).values_list("pk", flat=True))
    interviewed = set(metrics.interviewed(ctx).values_list("pk", flat=True))
    applications: dict[int, set[int]] = defaultdict(set)
    names: dict[int, str] = {}
    records = ApplicationDocument.objects.filter(application__in=sent_ids).select_related(
        "document_version__document__document_type"
    )
    for record in records:
        version = record.document_version
        applications[version.pk].add(record.application_id)
        names[version.pk] = f"{version} ({version.document.document_type})"
    rows = [
        Row(names[pk], len(ids), len(ids & responded), len(ids & interviewed))
        for pk, ids in applications.items()
    ]
    return sorted(rows, key=lambda row: (-row.sent, row.label))


@widget(
    "documents",
    "Performance by document version",
    "Which CV or cover letter version gets more answers? (Versions sent with applications "
    "of this period.)",
    "performance.html",
    size="full",
)
def documents(ctx: FilterContext, links: Links) -> dict[str, Any]:
    return _performance(
        document_rows(ctx),
        "No documents recorded as sent for this period. Record them on an application's page.",
    )


# --- by job profile --------------------------------------------------------------------------


@widget(
    "profiles",
    "Performance by job profile",
    "Which kinds of jobs answer you: work mode, employment type, seniority.",
    "performance.html",
)
def profiles(ctx: FilterContext, links: Links) -> dict[str, Any]:
    sections = []
    all_rows: list[Row] = []
    for title, field, choices, param in (
        ("Work mode", "posting__remote_type", RemoteType.choices, "remote_type"),
        ("Employment", "posting__employment_type", EmploymentType.choices, "employment_type"),
        ("Seniority", "posting__seniority", Seniority.choices, ""),
    ):
        labels: dict[Any, str] = {**dict(choices), "": "Not set"}
        rows = rows_by(ctx, field, labels, link_param=param, links=links)
        if rows:
            sections.append({"title": title, "rows": rows})
            all_rows += [
                Row(f"{title}: {r.label}", r.sent, r.responded, r.interviewed) for r in rows
            ]
    return {
        "sections": sections,
        "empty_text": "No applications sent in this period.",
        "min_sample": MIN_SAMPLE,
        "table": Table(ROW_HEADERS, [row.table_row() for row in all_rows]),
    }


# --- rejections ------------------------------------------------------------------------------


@widget(
    "rejections",
    "Rejections",
    "Rejected applications of the period: how far they got, and the reasons given.",
    "rejections.html",
)
def rejections(ctx: FilterContext, links: Links) -> dict[str, Any]:
    rejected = metrics.rejected(ctx)
    stage_names = dict(PipelineStage.objects.values_list("pk", "name"))
    by_stage = Counter(rejected.values_list("outcome_stage", flat=True))
    reasons = Counter(rejected.values_list("rejection_reason", flat=True))
    reason_labels = {**dict(RejectionReason.choices), "": "Not recorded"}
    stage_items = [
        (stage_names.get(pk, "Unknown"), n, str(n), "", "") for pk, n in by_stage.most_common()
    ]
    reason_items = [(reason_labels[r], n, str(n), "", "") for r, n in reasons.most_common()]
    rows = [("Got as far as", label, text) for label, _, text, _, _ in stage_items]
    rows += [("Reason", label, text) for label, _, text, _, _ in reason_items]
    return {
        "total": sum(by_stage.values()),
        "url": links.group("rejected"),
        "stages": bars(stage_items),
        "reasons": bars(reason_items),
        "table": Table(("Grouped by", "Value", "Rejections"), rows),
    }


# --- time in stage ---------------------------------------------------------------------------


def stage_durations(applications: QuerySet[Application]) -> dict[int, list[float]]:
    """Days each application spent in each stage, from its stage-change timeline.

    A stay is complete when a later stage change ends it; the current, open stay is left
    out (it isn't over yet, so it would make stages look shorter than they are).
    """
    events = (
        ApplicationEvent.objects.filter(application__in=applications, kind=EventKind.STAGE_CHANGE)
        .order_by("application_id", "occurred_at", "pk")
        .values_list("application_id", "to_stage_id", "occurred_at")
    )
    durations: dict[int, list[float]] = defaultdict(list)
    previous: tuple[int, int | None, Any] | None = None
    for application_id, stage_id, occurred_at in events:
        if previous is not None and previous[0] == application_id and previous[1] is not None:
            days = (occurred_at - previous[2]).total_seconds() / 86400
            durations[previous[1]].append(max(days, 0))
        previous = (application_id, stage_id, occurred_at)
    return durations


@widget(
    "time_in_stage",
    "Time in stage",
    "Average days an application stayed in a stage before it moved on.",
    "bar_list.html",
)
def time_in_stage(ctx: FilterContext, links: Links) -> dict[str, Any]:
    durations = stage_durations(ctx.sent())
    # Only stages an application passes THROUGH: the question is "where does it stall?".
    # (Leaving a final stage only happens when an application is reopened.)
    stages = (
        PipelineStage.objects.filter(pk__in=durations)
        .exclude(category__in=FINAL_CATEGORIES)
        .order_by("order", "pk")
    )
    items = []
    for stage in stages:
        days = durations[stage.pk]
        average = mean(days)
        items.append((stage.name, average, f"{average:.1f} d", "", f"{len(days)} moves"))
    table = Table(
        ("Stage", "Average days", "Moves"),
        [(label, text, note) for label, _, text, _, note in items],
    )
    return {
        "bars": bars(items),
        "empty_text": "No stage changes yet for the applications of this period.",
        "table": table,
    }


# --- weekday ---------------------------------------------------------------------------------

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@widget(
    "weekday",
    "Applications by weekday",
    "On which days you apply, and how often those applications got an answer.",
    "column_chart.html",
)
def weekday(ctx: FilterContext, links: Links) -> dict[str, Any]:
    # "Sent" applications always have applied_on; the "if" only tells mypy so.
    sent_days = [(pk, day) for pk, day in ctx.sent().values_list("pk", "applied_on") if day]
    responded = set(metrics.responded(ctx).values_list("pk", flat=True))
    sent_per_day: Counter[int] = Counter()
    answered_per_day: Counter[int] = Counter()
    for pk, day in sent_days:
        sent_per_day[day.weekday()] += 1
        answered_per_day[day.weekday()] += pk in responded
    top = max(sent_per_day.values(), default=0) or 1
    columns = [
        Bar(
            label=name,
            value=sent_per_day[i],
            text=str(sent_per_day[i]),
            share=sent_per_day[i] / top,
            note=percent(answered_per_day[i] / sent_per_day[i]) if sent_per_day[i] else "—",
        )
        for i, name in enumerate(WEEKDAYS)
    ]
    table = Table(
        ("Weekday", "Applications", "Response rate"), [(c.label, c.text, c.note) for c in columns]
    )
    return {
        "columns": columns if sent_per_day else [],
        "goal_target": 0,
        "show_values": True,
        "label_every": 1,
        "note_label": "answered",
        "table": table,
    }


# --- activity heatmap ------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    day: date
    count: int
    level: int  # 0 (none) .. 5 (most)
    in_period: bool

    @property
    def classes(self) -> str:
        return HEAT_CLASSES[self.level]


# Full class names for Tailwind (see widgets.SLOT_CLASSES). Level 0 = no activity.
HEAT_CLASSES = (
    "bg-surface-muted",
    "bg-chart-heat-1",
    "bg-chart-heat-2",
    "bg-chart-heat-3",
    "bg-chart-heat-4",
    "bg-chart-heat-5",
)


@widget(
    "activity",
    "Activity",
    "What you did per day: applications sent and everything on the timelines.",
    "heatmap.html",
    size="full",
)
def activity(ctx: FilterContext, links: Links) -> dict[str, Any]:
    events = ApplicationEvent.objects.filter(application__in=ctx.applications())
    first = events.order_by("occurred_at").values_list("occurred_at", flat=True).first()
    weeks = weeks_of(ctx.period, timezone.localdate(first) if first else None)
    start = weeks[0].start or ctx.period.end
    per_day = Counter(
        timezone.localdate(moment)
        for moment in events.filter(occurred_at__date__gte=start - timedelta(days=1)).values_list(
            "occurred_at", flat=True
        )
    )
    top = max(per_day.values(), default=0)
    grid = []
    for week in weeks:
        cells = []
        for offset in range(7):
            day = (week.start or start) + timedelta(days=offset)
            count = per_day.get(day, 0) if day <= ctx.period.end else 0
            level = 0 if not count or not top else max(1, -(-count * 5 // top))  # ceil
            cells.append(Cell(day, count, level, ctx.period.contains(day)))
        grid.append(cells)
    active_days = [(c.day, c.count) for week in grid for c in week if c.count]
    return {
        "grid": grid,
        "weekdays": WEEKDAYS,
        "levels": HEAT_CLASSES[1:],
        "total": sum(count for _, count in active_days),
        "table": Table(("Day", "Activities"), [(f"{d:%d %b %Y}", str(n)) for d, n in active_days]),
    }


# --- salaries --------------------------------------------------------------------------------

SALARY_ROWS = 12


@dataclass(frozen=True)
class SalaryRow:
    label: str
    url: str
    low: int | None  # advertised range (yearly)
    high: int | None
    expected: int | None
    scale_min: int
    scale_max: int

    def _position(self, amount: int) -> float:
        span = self.scale_max - self.scale_min or 1
        return (amount - self.scale_min) / span

    @property
    def range_start(self) -> float:
        return self._position(self.low or self.high or 0)

    @property
    def range_width(self) -> float:
        low, high = self.low or self.high, self.high or self.low
        return 0.0 if low is None or high is None else self._position(high) - self._position(low)

    @property
    def expected_at(self) -> float:
        return self._position(self.expected) if self.expected else 0.0


@widget(
    "salary",
    "Salaries",
    "Advertised yearly ranges vs. your salary expectation (in your default currency).",
    "salary.html",
    size="full",
)
def salary(ctx: FilterContext, links: Links) -> dict[str, Any]:
    currency = UserSettings.load().default_currency
    with_salary = (
        ctx.sent()
        .select_related("posting__company")
        .filter(
            Q(salary_expectation__isnull=False, salary_expectation_currency=currency)
            | Q(
                posting__salary_period=SalaryPeriod.YEAR,
                posting__salary_currency=currency,
            )
            & (Q(posting__salary_min__isnull=False) | Q(posting__salary_max__isnull=False))
        )
        .order_by("-applied_on", "-pk")[:SALARY_ROWS]
    )
    raw = []
    for application in with_salary:
        posting = application.posting
        yearly = posting.salary_period == SalaryPeriod.YEAR and posting.salary_currency == currency
        expected = (
            application.salary_expectation
            if application.salary_expectation_currency == currency
            else None
        )
        raw.append(
            (
                f"{posting.title} · {posting.company_display or 'Unknown company'}",
                application.get_absolute_url(),
                posting.salary_min if yearly else None,
                posting.salary_max if yearly else None,
                expected,
            )
        )
    amounts = [a for _, _, low, high, exp in raw for a in (low, high, exp) if a]
    if not amounts:
        return {"rows": [], "table": Table(("Application", "Advertised", "Expected"), [])}
    scale_min, scale_max = min(amounts), max(amounts)
    rows = [SalaryRow(*item, scale_min=scale_min, scale_max=scale_max) for item in raw]
    midpoints = [
        ((r.low or r.high or 0) + (r.high or r.low or 0)) / 2 for r in rows if r.low or r.high
    ]
    expectations = [r.expected for r in rows if r.expected]

    def money(amount: float | None) -> str:
        return "—" if amount is None else f"{amount:,.0f} {currency}"

    table = Table(
        ("Application", "Advertised from", "Advertised up to", "Your expectation"),
        [(r.label, money(r.low), money(r.high), money(r.expected)) for r in rows],
    )
    return {
        "rows": rows,
        "scale_min": money(scale_min),
        "scale_max": money(scale_max),
        "median_advertised": money(median(midpoints)) if midpoints else "—",
        "median_expected": money(median(expectations)) if expectations else "—",
        "table": table,
    }
