"""The dashboard's building blocks: a registry of widgets.

A widget = a title, a size, a template, and a function that computes its data for a
FilterContext. Every widget also returns its data as a Table: shown as "Show as table"
under the chart (so no value is only readable from colour or hover) and used for the
CSV export. The dashboard simply renders the widgets in layout order.

Charts are drawn as plain HTML (bars are divs with a width or height in %), styled with
the design tokens, so they follow light/dark mode and HTMX updates without JavaScript.
See docs/adr/0007-dashboard-charts-server-rendered.md.
"""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from urllib.parse import urlencode

from django.db.models import Count, Q
from django.urls import reverse

from organizer.applications.models import PipelineStage

from . import metrics
from .filters import FilterContext, Period
from .goals import goal_progress
from .metrics import GROUPS, Unit, compare
from .models import Goal, GoalPeriod

# --- shared pieces -----------------------------------------------------------------------


@dataclass(frozen=True)
class Table:
    """The widget's data as rows of text: the table view and the CSV export."""

    headers: tuple[str, ...]
    rows: Sequence[tuple[str, ...]]


@dataclass(frozen=True)
class Bar:
    """One bar of a bar list or column chart."""

    label: str
    value: float
    text: str  # the value as shown, e.g. "12" or "67%"
    share: float  # 0..1: the bar's length relative to the longest bar
    url: str = ""  # drill-down link
    note: str = ""  # a second, quieter text, e.g. "8 of 12"


def bars(items: Sequence[tuple[str, float, str, str, str]]) -> list[Bar]:
    """(label, value, text, url, note) → Bars with their relative length."""
    longest = max((value for _, value, _, _, _ in items), default=0) or 1
    return [
        Bar(label, value, text, value / longest, url, note)
        for label, value, text, url, note in items
    ]


def percent(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


@dataclass(frozen=True)
class Widget:
    key: str
    title: str
    description: str
    template: str
    build: Callable[["FilterContext", "Links"], dict[str, Any]]
    size: str = "half"  # "half" or "full" width (the layout can override it, batch D)


WIDGETS: dict[str, Widget] = {}


def widget(
    key: str, title: str, description: str, template: str, *, size: str = "half"
) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
    def register(build: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        if key in WIDGETS:
            raise ValueError(f"A widget called {key!r} is already registered.")
        WIDGETS[key] = Widget(key, title, description, f"analytics/widgets/{template}", build, size)
        return build

    return register


@dataclass(frozen=True)
class Links:
    """Builds drill-down URLs that keep the dashboard's current filters."""

    query: dict[str, str] = field(default_factory=dict)  # the dashboard's filter values

    def group(self, key: str, **overrides: str) -> str:
        params = {**self.query, **overrides, "group": key}
        return f"{reverse('analytics:drilldown')}?{urlencode(params)}"

    def period(self, key: str, period: Period) -> str:
        """The same group for another period (e.g. one week of the weekly chart)."""
        return self.group(key, range="custom", start=_iso(period.start), end=period.end.isoformat())


def _iso(day: date | None) -> str:
    return "" if day is None else day.isoformat()


# --- KPI tiles ---------------------------------------------------------------------------

KPI_KEYS = (
    "applications_sent",
    "response_rate",
    "interview_rate",
    "offer_rate",
    "ghosting_rate",
    "days_to_first_response",
    "active_pipeline",
    "follow_ups_due",
)


@dataclass(frozen=True)
class Tile:
    label: str
    value: str
    detail: str  # e.g. "8 of 12" or "right now"
    change: str  # e.g. "+5 pts", "" if there is nothing to compare
    is_good: bool | None
    direction: str  # "up", "down" or ""
    description: str
    url: str


def format_value(result: metrics.MetricResult) -> str:
    if result.value is None:
        return "—"
    if result.unit == Unit.PERCENT:
        return percent(result.value)
    if result.unit == Unit.DAYS:
        return f"{result.value:g} d"
    return f"{int(result.value):,}"


def format_change(unit: str, change: float) -> str:
    sign = "+" if change > 0 else "\u2212"  # U+2212, a real minus sign (not a hyphen)
    size = abs(change)
    if unit == Unit.PERCENT:
        return f"{sign}{size * 100:.0f} pts"  # percentage POINTS, not percent
    if unit == Unit.DAYS:
        return f"{sign}{size:g} d"
    return f"{sign}{size:,.0f}"


def tile(key: str, ctx: FilterContext, links: Links) -> Tile:
    comparison = compare(key, ctx)
    metric, result = comparison.metric, comparison.current
    if not metric.comparable:
        detail = "right now"
    elif result.unit == Unit.PERCENT and result.denominator:
        detail = f"{result.numerator} of {result.denominator}"
    elif result.unit == Unit.DAYS and result.numerator:
        detail = f"average of {result.numerator}"
    else:
        detail = ""
    change = comparison.change
    return Tile(
        label=metric.label,
        value=format_value(result),
        detail=detail,
        change="" if not change else format_change(result.unit, change),
        is_good=comparison.is_good,
        direction="" if not change else ("up" if change > 0 else "down"),
        description=metric.description,
        url=links.group(metric.group) if metric.group else "",
    )


@widget(
    "kpis",
    "Key numbers",
    "The headline numbers, compared with the period before.",
    "kpis.html",
    size="full",
)
def kpis(ctx: FilterContext, links: Links) -> dict[str, Any]:
    tiles = [tile(key, ctx, links) for key in KPI_KEYS]
    table = Table(
        ("Metric", "Value", "Detail", "Change"),
        [(t.label, t.value, t.detail, t.change) for t in tiles],
    )
    return {"tiles": tiles, "compared": ctx.previous() is not None, "table": table}


# --- goal ----------------------------------------------------------------------------------


@widget("goal", "Goal", "Your weekly or monthly target and how far along you are.", "goal.html")
def goal(ctx: FilterContext, links: Links) -> dict[str, Any]:
    progress = goal_progress(ctx)
    rows = [(str(p.goal), str(p.done), str(p.remaining), percent(p.ratio)) for p in progress]
    return {
        "progress": progress,
        "periods": GoalPeriod.choices,
        "this_week_url": links.period("sent", progress[0].period) if progress else "",
        "table": Table(("Goal", "Done", "Remaining", "Progress"), rows),
    }


# --- funnel --------------------------------------------------------------------------------


@widget(
    "funnel",
    "Funnel",
    "Of the applications sent in the period: how far did they get?",
    "bar_list.html",
)
def funnel(ctx: FilterContext, links: Links) -> dict[str, Any]:
    steps = ["sent", "responded", "interviewed", "offered"]
    counts = [GROUPS[key].members(ctx).count() for key in steps]
    sent_count = counts[0]
    items = []
    for key, count in zip(steps, counts, strict=True):
        share = count / sent_count if sent_count else None
        note = "" if key == "sent" else f"{percent(share)} of sent"
        items.append((GROUPS[key].label, count, str(count), links.group(key), note))
    table = Table(
        ("Step", "Applications", "Share of sent"),
        [(label, text, note or "100%") for label, _, text, _, note in items],
    )
    return {
        "bars": bars(items) if sent_count else [],
        "empty_text": "No applications sent in this period.",
        "table": table,
    }


# --- applications per week -----------------------------------------------------------------

MAX_WEEKS = 26


def weeks_of(period: Period, first_day: date | None) -> list[Period]:
    """Calendar weeks (Monday-Sunday) covering the period, at most the last 26."""
    start = period.start or first_day or period.end
    monday = start - timedelta(days=start.weekday())
    weeks = []
    while monday <= period.end:
        weeks.append(Period(monday, monday + timedelta(days=6)))
        monday += timedelta(days=7)
    return weeks[-MAX_WEEKS:]


@widget(
    "weekly",
    "Applications per week",
    "Applications sent per calendar week, with your goal.",
    "column_chart.html",
    size="full",
)
def weekly(ctx: FilterContext, links: Links) -> dict[str, Any]:
    sent_days = list(ctx.sent().values_list("applied_on", flat=True))
    weeks = weeks_of(ctx.period, min((d for d in sent_days if d), default=None))
    per_week = Counter(d - timedelta(days=d.weekday()) for d in sent_days if d)
    weekly_goal = Goal.objects.filter(is_active=True, period=GoalPeriod.WEEK).first()
    target = weekly_goal.target if weekly_goal else 0
    top = max([*(per_week[w.start] for w in weeks if w.start), target, 1])
    columns = [
        Bar(
            label=f"{week.start:%d %b}" if week.start else "",
            value=per_week[week.start],
            text=str(per_week[week.start]),
            share=per_week[week.start] / top,
            url=links.period("sent", week),
            note=f"Week {week.start.isocalendar().week}" if week.start else "",
        )
        for week in weeks
        if week.start is not None
    ]
    table = Table(("Week starting", "Applications"), [(c.label, c.text) for c in columns])
    return {
        "columns": columns,
        "goal_target": target,
        "goal_share": target / top if target else 0,
        "show_values": len(columns) <= 14,  # value on every cap only while it's readable
        "label_every": max(1, -(-len(columns) // 9)),  # at most ~9 date labels (ceil)
        "table": table,
    }


# --- pipeline by stage ---------------------------------------------------------------------


@widget(
    "pipeline", "Pipeline by stage", "Your open applications right now, by stage.", "bar_list.html"
)
def pipeline(ctx: FilterContext, links: Links) -> dict[str, Any]:
    stages = (
        PipelineStage.objects.filter(category__in=metrics.OPEN_CATEGORIES)
        .annotate(open=Count("applications", filter=Q(applications__in=metrics.active(ctx))))
        .order_by("order", "pk")
    )
    list_url = reverse("applications:list")
    items = [
        (s.name, s.open, str(s.open), f"{list_url}?{urlencode({'stage': s.pk})}", "")
        for s in stages
    ]
    table = Table(("Stage", "Open applications"), [(i[0], i[2]) for i in items])
    return {
        "bars": bars(items) if any(i[1] for i in items) else [],
        "empty_text": "No open applications right now.",
        "table": table,
    }


# --- outcomes ------------------------------------------------------------------------------

# Fixed order = fixed colour slot (chart-1 ... chart-5): an outcome keeps its colour even
# when another one is missing. The order was checked with the colour validator.
OUTCOMES = ("waiting", "rejected", "accepted", "ghosted", "withdrawn")


# Full class names (Tailwind only finds classes written out completely in the code; a
# name built at runtime like f"bg-chart-{slot}" would get no CSS). Text inside a block is
# white, except on yellow (slot 4), as the colour validator's reference says.
SLOT_CLASSES = (
    "bg-chart-1 text-chart-on-fill",
    "bg-chart-2 text-chart-on-fill",
    "bg-chart-3 text-chart-on-fill",
    "bg-chart-4 text-chart-on-4",
    "bg-chart-5 text-chart-on-fill",
)
SWATCH_CLASSES = ("bg-chart-1", "bg-chart-2", "bg-chart-3", "bg-chart-4", "bg-chart-5")


@dataclass(frozen=True)
class Segment:
    key: str
    label: str
    count: int
    share: float
    slot: int  # colour slot 1..5
    url: str

    @property
    def share_text(self) -> str:
        return percent(self.share)

    @property
    def classes(self) -> str:
        return SLOT_CLASSES[self.slot - 1]

    @property
    def swatch(self) -> str:
        return SWATCH_CLASSES[self.slot - 1]

    @property
    def fits_label(self) -> bool:
        """Print the share inside the block only where it fits (else: legend + table)."""
        return self.share >= 0.12


@widget(
    "outcomes",
    "Outcomes",
    "How the applications sent in the period ended (so far).",
    "segmented_bar.html",
)
def outcomes(ctx: FilterContext, links: Links) -> dict[str, Any]:
    counts = {key: GROUPS[key].members(ctx).count() for key in OUTCOMES}
    total = sum(counts.values())
    segments = [
        Segment(
            key,
            GROUPS[key].label,
            counts[key],
            counts[key] / total if total else 0,
            slot,
            links.group(key),
        )
        for slot, key in enumerate(OUTCOMES, start=1)
    ]
    table = Table(
        ("Outcome", "Applications", "Share"),
        [(s.label, str(s.count), percent(s.share)) for s in segments],
    )
    return {"segments": segments, "total": total, "table": table}


# --- the default layout ----------------------------------------------------------------------

DEFAULT_LAYOUT = (
    # batch B: the overview
    "insights",
    "kpis",
    "goal",
    "funnel",
    "weekly",
    "pipeline",
    "outcomes",
    # batch C: what works? (registered in performance.py and insights.py)
    "documents",
    "sources",
    "channels",
    "profiles",
    "rejections",
    "time_in_stage",
    "weekday",
    "activity",
    "salary",
)


def render_data(keys: tuple[str, ...], ctx: FilterContext, links: Links) -> list[dict[str, Any]]:
    """Each widget with its computed data, in this order (unknown keys are skipped)."""
    return [
        {"widget": WIDGETS[key], **WIDGETS[key].build(ctx, links)} for key in keys if key in WIDGETS
    ]
