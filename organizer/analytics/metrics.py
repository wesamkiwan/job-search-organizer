"""The dashboard's numbers: a registry of metric functions.

A metric is a function FilterContext → MetricResult, registered with @metric(...):

    @metric("response_rate", "Response rate", Unit.PERCENT)
    def response_rate(ctx: FilterContext) -> MetricResult: ...

The registry (a dict: key → Metric) lets the dashboard ask for metrics by name, list them
for the layout editor and attach a description, without a long if/elif chain. Adding a
metric = writing one function; nothing else changes. All counting happens in the
database (Count/Exists/Min); only small final steps (averages of day differences) run
in Python.

Definitions (also shown as tooltips later):
  - "sent": applied_on inside the period. Every rate is "of the applications sent in
    the period, how many ..." (whenever the answer came).
  - response: reached a stage after "applied" that is not ghosted or withdrawn (a
    rejection IS a response), or an "Email received" entry on the timeline.
  - interview: reached a stage with counts_as_interview, or an offer (an offer without
    an interview is rare, and the funnel must not go up again).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from statistics import mean

from django.db import models
from django.db.models import Exists, Min, OuterRef, Q, QuerySet
from django.utils import timezone

from organizer.applications.models import (
    Application,
    ApplicationEvent,
    EventKind,
    PipelineStage,
    StageCategory,
    Task,
)
from organizer.core.models import UserSettings
from organizer.jobs.models import TriageStatus

from .filters import FilterContext


class Unit(models.TextChoices):
    COUNT = "count", "Count"
    PERCENT = "percent", "Percent"  # value is a fraction 0..1; templates show 0.25 as 25%
    DAYS = "days", "Days"


@dataclass(frozen=True)
class MetricResult:
    """One number. value=None means "not enough data" (e.g. a rate of 0 applications),
    which is NOT the same as 0. For rates, numerator/denominator are kept for tooltips
    ("3 of 12") and for the minimum-sample rules of the insights panel (batch C)."""

    value: float | None
    unit: str
    numerator: int | None = None
    denominator: int | None = None


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    description: str
    compute: Callable[[FilterContext], MetricResult]
    # False for snapshots ("right now"), which have no "previous period" to compare with.
    comparable: bool = True
    # For the trend arrow's colour: is going up good (green) or bad (red)?
    higher_is_better: bool = True


REGISTRY: dict[str, Metric] = {}


def metric(
    key: str,
    label: str,
    unit: str,
    description: str,
    *,
    comparable: bool = True,
    higher_is_better: bool = True,
) -> Callable[[Callable[[FilterContext], MetricResult]], Callable[[FilterContext], MetricResult]]:
    """Decorator that registers a metric function under `key`.

    A decorator is a function that receives the decorated function. This one stores it
    in REGISTRY and returns it unchanged, so it can still be called directly in tests.
    """

    def register(
        compute: Callable[[FilterContext], MetricResult],
    ) -> Callable[[FilterContext], MetricResult]:
        if key in REGISTRY:
            raise ValueError(f"A metric called {key!r} is already registered.")
        REGISTRY[key] = Metric(key, label, unit, description, compute, comparable, higher_is_better)
        return compute

    return register


# --- comparing with the previous period --------------------------------------------------


@dataclass(frozen=True)
class Comparison:
    metric: Metric
    current: MetricResult
    previous: MetricResult | None  # None: nothing to compare with

    @property
    def change(self) -> float | None:
        """current - previous (percentage POINTS for rates), or None if unknown."""
        if self.previous is None or self.current.value is None or self.previous.value is None:
            return None
        return self.current.value - self.previous.value

    @property
    def is_good(self) -> bool | None:
        """Is the change good news? None when there is no change to judge."""
        if not self.change:  # None or exactly 0
            return None
        return (self.change > 0) == self.metric.higher_is_better


def compare(key: str, ctx: FilterContext) -> Comparison:
    """A metric for the context, and (if it makes sense) for the previous period."""
    found = REGISTRY[key]
    current = found.compute(ctx)
    previous_ctx = ctx.previous() if found.comparable else None
    previous = found.compute(previous_ctx) if previous_ctx is not None else None
    return Comparison(found, current, previous)


# --- building blocks ---------------------------------------------------------------------

OPEN_CATEGORIES = (StageCategory.APPLIED, StageCategory.IN_PROGRESS, StageCategory.OFFER)
OFFER_CATEGORIES = (StageCategory.OFFER, StageCategory.WON)
# Stages that only an employer's answer can lead to.
RESPONSE_STAGES = Q(
    category__in=(StageCategory.IN_PROGRESS, *OFFER_CATEGORIES, StageCategory.LOST)
) & Q(counts_as_ghosted=False)
INTERVIEW_STAGES = Q(counts_as_interview=True) | Q(category__in=OFFER_CATEGORIES)
OFFER_STAGES = Q(category__in=OFFER_CATEGORIES)


def _reached(stages: Q) -> Q:
    """Applications that are in one of these stages now, or ever moved into one.

    Exists(...) is a subquery "is there at least one such event for this application?"
    (OuterRef("pk") = the application of the outer query). Unlike a JOIN it never
    duplicates rows. The current stage is checked too, for applications without history.
    """
    matching = PipelineStage.objects.filter(stages)
    moved_there = ApplicationEvent.objects.filter(
        application=OuterRef("pk"), kind=EventKind.STAGE_CHANGE, to_stage__in=matching
    )
    return Q(Exists(moved_there)) | Q(stage__in=matching)


def _responded() -> Q:
    email_received = ApplicationEvent.objects.filter(
        application=OuterRef("pk"), kind=EventKind.EMAIL_RECEIVED
    )
    return _reached(RESPONSE_STAGES) | Q(Exists(email_received))


def _rate(part: QuerySet[Application], whole: QuerySet[Application]) -> MetricResult:
    numerator, denominator = part.count(), whole.count()
    value = numerator / denominator if denominator else None
    return MetricResult(value, Unit.PERCENT, numerator, denominator)


def _average_days_until(applications: QuerySet[Application], events: Q) -> MetricResult:
    """Average days from applied_on to the first matching timeline event."""
    with_first = applications.annotate(first=Min("events__occurred_at", filter=events)).filter(
        first__isnull=False
    )
    days = [
        max((timezone.localdate(first) - applied_on).days, 0)
        for applied_on, first in with_first.values_list("applied_on", "first")
        if applied_on is not None  # always true for "sent" applications; tells mypy so
    ]
    return MetricResult(round(mean(days), 1) if days else None, Unit.DAYS, len(days), None)


def _stage_events(stages: Q) -> Q:
    # Q on the related events: used inside Min(..., filter=...) above.
    return Q(
        events__kind=EventKind.STAGE_CHANGE,
        events__to_stage__in=PipelineStage.objects.filter(stages),
    )


# --- the metrics -------------------------------------------------------------------------


@metric("applications_sent", "Applications sent", Unit.COUNT, "Applied in the period.")
def applications_sent(ctx: FilterContext) -> MetricResult:
    return MetricResult(ctx.sent().count(), Unit.COUNT)


@metric(
    "response_rate",
    "Response rate",
    Unit.PERCENT,
    "Sent in the period and answered by the employer (incl. rejections).",
)
def response_rate(ctx: FilterContext) -> MetricResult:
    sent = ctx.sent()
    return _rate(sent.filter(_responded()), sent)


@metric(
    "interview_rate",
    "Interview rate",
    Unit.PERCENT,
    "Sent in the period and invited to an interview (or got an offer).",
)
def interview_rate(ctx: FilterContext) -> MetricResult:
    sent = ctx.sent()
    return _rate(sent.filter(_reached(INTERVIEW_STAGES)), sent)


@metric("offer_rate", "Offer rate", Unit.PERCENT, "Sent in the period and got an offer.")
def offer_rate(ctx: FilterContext) -> MetricResult:
    sent = ctx.sent()
    return _rate(sent.filter(_reached(OFFER_STAGES)), sent)


@metric(
    "rejection_rate",
    "Rejection rate",
    Unit.PERCENT,
    "Sent in the period and now rejected (lost, not ghosted).",
    higher_is_better=False,
)
def rejection_rate(ctx: FilterContext) -> MetricResult:
    sent = ctx.sent()
    rejected = sent.filter(stage__category=StageCategory.LOST, stage__counts_as_ghosted=False)
    return _rate(rejected, sent)


@metric(
    "ghosting_rate",
    "Ghosting rate",
    Unit.PERCENT,
    "Sent in the period and marked as ghosted, or still open without any answer after the "
    "number of days set in Settings.",
    higher_is_better=False,
)
def ghosting_rate(ctx: FilterContext) -> MetricResult:
    sent = ctx.sent()
    cutoff = ctx.today - timedelta(days=UserSettings.load().ghosted_after_days)
    silent_too_long = Q(closed_at__isnull=True, applied_on__lte=cutoff) & ~_responded()
    return _rate(sent.filter(Q(stage__counts_as_ghosted=True) | silent_too_long), sent)


@metric(
    "days_to_first_response",
    "Days to first response",
    Unit.DAYS,
    "Average days from applying to the employer's first answer (sent in the period).",
    higher_is_better=False,
)
def days_to_first_response(ctx: FilterContext) -> MetricResult:
    response_events = _stage_events(RESPONSE_STAGES) | Q(events__kind=EventKind.EMAIL_RECEIVED)
    return _average_days_until(ctx.sent(), response_events)


@metric(
    "days_to_offer",
    "Days to offer",
    Unit.DAYS,
    "Average days from applying to an offer (sent in the period).",
    higher_is_better=False,
)
def days_to_offer(ctx: FilterContext) -> MetricResult:
    return _average_days_until(ctx.sent(), _stage_events(OFFER_STAGES))


@metric(
    "active_pipeline",
    "Active pipeline",
    Unit.COUNT,
    "Open applications right now: applied, in progress or with an offer.",
    comparable=False,
)
def active_pipeline(ctx: FilterContext) -> MetricResult:
    active = ctx.applications().filter(closed_at__isnull=True, stage__category__in=OPEN_CATEGORIES)
    return MetricResult(active.count(), Unit.COUNT)


@metric(
    "follow_ups_due",
    "Follow-ups due",
    Unit.COUNT,
    "Open applications whose follow-up date has come, plus open tasks that are due.",
    comparable=False,
    higher_is_better=False,
)
def follow_ups_due(ctx: FilterContext) -> MetricResult:
    applications = ctx.applications()
    due_applications = applications.filter(closed_at__isnull=True, follow_up_on__lte=ctx.today)
    due_tasks = Task.objects.filter(done_at__isnull=True, due_on__lte=ctx.today).filter(
        Q(application__in=applications) | Q(application__isnull=True)
    )
    return MetricResult(due_applications.count() + due_tasks.count(), Unit.COUNT)


@metric(
    "inbox_backlog",
    "New postings",
    Unit.COUNT,
    "Job postings you haven't looked at yet.",
    comparable=False,
    higher_is_better=False,
)
def inbox_backlog(ctx: FilterContext) -> MetricResult:
    return MetricResult(ctx.postings().filter(triage_status=TriageStatus.NEW).count(), Unit.COUNT)
