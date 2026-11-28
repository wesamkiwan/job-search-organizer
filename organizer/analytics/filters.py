"""What the dashboard looks at: a period of time plus optional filters.

Every metric receives one FilterContext and answers its question for exactly those
applications. The same object later drives the filter bar (batch B), so "which
applications count?" is decided in one place.
"""

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone

from organizer.applications.models import Application
from organizer.jobs.models import JobPosting


class Preset(models.TextChoices):
    """The quick choices for the date range."""

    LAST_7_DAYS = "7d", "Last 7 days"
    LAST_30_DAYS = "30d", "Last 30 days"
    LAST_90_DAYS = "90d", "Last 90 days"
    THIS_MONTH = "month", "This month"
    ALL_TIME = "all", "All time"
    CUSTOM = "custom", "Custom range"


@dataclass(frozen=True)
class Period:
    """A range of days, both ends included. start=None means "since the beginning"."""

    start: date | None
    end: date

    @property
    def days(self) -> int | None:
        return None if self.start is None else (self.end - self.start).days + 1

    def previous(self) -> "Period | None":
        """The period of the same length just before this one, for "compared with ...".
        E.g. 1-30 Nov → 2-31 Oct. "All time" has nothing before it."""
        if self.start is None or self.days is None:
            return None
        end = self.start - timedelta(days=1)
        return Period(end - timedelta(days=self.days - 1), end)

    def contains(self, day: date) -> bool:
        return (self.start is None or self.start <= day) and day <= self.end


def period_for(
    preset: str,
    *,
    today: date | None = None,
    start: date | None = None,
    end: date | None = None,
) -> Period:
    """Turn a preset (or a custom start/end) into a Period. Unknown presets → 30 days."""
    today = today or timezone.localdate()
    if preset == Preset.LAST_7_DAYS:
        return Period(today - timedelta(days=6), today)
    if preset == Preset.LAST_90_DAYS:
        return Period(today - timedelta(days=89), today)
    if preset == Preset.THIS_MONTH:
        return Period(today.replace(day=1), today)
    if preset == Preset.ALL_TIME:
        return Period(None, today)
    if preset == Preset.CUSTOM and end is not None:
        if start is not None and start > end:
            start, end = end, start  # swapped by mistake: be forgiving
        return Period(start, end)
    return Period(today - timedelta(days=29), today)  # LAST_30_DAYS and the fallback


@dataclass(frozen=True)
class FilterContext:
    """The period and the filters of one dashboard view. Empty filters mean "all".

    frozen=True: a FilterContext never changes; replace() makes a changed copy (used for
    the previous period). That also makes it safe to use as a cache key later.
    """

    period: Period
    today: date = field(default_factory=timezone.localdate)
    sources: tuple[int, ...] = ()  # Source ids
    channels: tuple[str, ...] = ()  # Channel values
    tags: tuple[int, ...] = ()  # Tag ids
    remote_types: tuple[str, ...] = ()  # RemoteType values
    employment_types: tuple[str, ...] = ()  # EmploymentType values

    def previous(self) -> "FilterContext | None":
        """The same filters for the previous period (None for "all time")."""
        period = self.period.previous()
        return None if period is None else replace(self, period=period)

    # --- the querysets the metrics start from ---------------------------------------------

    def applications(self) -> QuerySet[Application]:
        """All applications matching the filters, in ANY period (for snapshots such as
        "active pipeline", which are about now, not about when you applied)."""
        applications = Application.objects.all()
        if self.sources:
            applications = applications.filter(posting__source__in=self.sources)
        if self.channels:
            applications = applications.filter(channel__in=self.channels)
        if self.remote_types:
            applications = applications.filter(posting__remote_type__in=self.remote_types)
        if self.employment_types:
            applications = applications.filter(posting__employment_type__in=self.employment_types)
        if self.tags:
            # A subquery, not filter(tags__in=...): through a many-to-many relation an
            # application with 2 matching tags would be counted twice.
            tagged = Application.objects.filter(tags__in=self.tags).values("pk")
            applications = applications.filter(pk__in=tagged)
        return applications

    def sent(self) -> QuerySet[Application]:
        """Applications SENT in the period (applied_on inside it): the group that every
        rate is about. "Response rate in November" = of the applications sent in
        November, how many got a response (whenever it came)."""
        sent = self.applications().filter(applied_on__isnull=False, applied_on__lte=self.period.end)
        if self.period.start is not None:
            sent = sent.filter(applied_on__gte=self.period.start)
        return sent

    def postings(self) -> QuerySet[JobPosting]:
        """Job postings matching the filters that a posting has (source, work mode,
        employment type). Channel and tags belong to applications, so they don't apply."""
        postings = JobPosting.objects.all()
        if self.sources:
            postings = postings.filter(source__in=self.sources)
        if self.remote_types:
            postings = postings.filter(remote_type__in=self.remote_types)
        if self.employment_types:
            postings = postings.filter(employment_type__in=self.employment_types)
        return postings
