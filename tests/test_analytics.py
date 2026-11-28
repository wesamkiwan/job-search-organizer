"""The dashboard's numbers: periods, filters, metrics and goals (Phase 3, batch A).

Scenarios are built with the real services (create, move, close; backdated), so the
metrics are tested on exactly the data the app produces.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from organizer.analytics import metrics
from organizer.analytics.filters import FilterContext, Period, Preset, period_for
from organizer.analytics.goals import goal_progress
from organizer.analytics.metrics import REGISTRY, MetricResult, Unit, compare
from organizer.analytics.models import Goal, GoalPeriod
from organizer.applications import services
from organizer.applications.models import (
    Application,
    Channel,
    EventKind,
    PipelineStage,
)
from organizer.core.models import UserSettings
from organizer.jobs.models import EmploymentType, RemoteType, TriageStatus
from tests.factories import (
    ApplicationFactory,
    JobPostingFactory,
    PipelineStageFactory,
    SourceFactory,
    TagFactory,
    TaskFactory,
    stage,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def at(day: date) -> datetime:
    """10:00 local time on that day, but never later than now: before 10 in the morning,
    "10:00 today" would be in the future, which the services rightly refuse (and the
    tests would pass in the afternoon and fail in the morning)."""
    return min(timezone.make_aware(datetime.combine(day, time(10))), timezone.now())


def apply(on: date, **posting: object) -> Application:
    """An application sent on that day (through the service, with its timeline)."""
    application = ApplicationFactory.build(
        posting=JobPostingFactory.create(**posting), stage=stage("Applied")
    )
    return services.create_application(application, occurred_at=at(on))


def move(application: Application, stage_name: str, on: date) -> None:
    services.change_stage(application, stage(stage_name), occurred_at=at(on))


def close(application: Application, stage_name: str, on: date) -> None:
    services.close_application(application, stage=stage(stage_name), occurred_at=at(on))


def email_received(application: Application, on: date) -> None:
    services.add_event(
        application, kind=EventKind.EMAIL_RECEIVED, summary="Reply", occurred_at=at(on)
    )


def last_30_days(**filters: Any) -> FilterContext:
    period = period_for(Preset.LAST_30_DAYS, today=TODAY)
    return FilterContext(period=period, today=TODAY, **filters)


def value(key: str, ctx: FilterContext) -> float | None:
    return REGISTRY[key].compute(ctx).value


# --- periods -----------------------------------------------------------------------------


def test_presets() -> None:
    today = date(2026, 11, 28)
    assert period_for(Preset.LAST_7_DAYS, today=today) == Period(date(2026, 11, 22), today)
    assert period_for(Preset.LAST_30_DAYS, today=today).days == 30
    assert period_for(Preset.LAST_90_DAYS, today=today).days == 90
    assert period_for(Preset.THIS_MONTH, today=today) == Period(date(2026, 11, 1), today)
    assert period_for(Preset.ALL_TIME, today=today) == Period(None, today)
    assert period_for("nonsense", today=today) == period_for(Preset.LAST_30_DAYS, today=today)


def test_custom_period_is_forgiving() -> None:
    start, end = date(2026, 10, 1), date(2026, 10, 31)
    assert period_for(Preset.CUSTOM, start=start, end=end) == Period(start, end)
    assert period_for(Preset.CUSTOM, start=end, end=start) == Period(start, end)  # swapped
    assert period_for(Preset.CUSTOM, end=end) == Period(None, end)  # open start
    # Without an end, a custom range falls back to the last 30 days.
    assert period_for(Preset.CUSTOM, start=start).days == 30


def test_previous_period_has_the_same_length() -> None:
    november = Period(date(2026, 11, 1), date(2026, 11, 30))
    assert november.previous() == Period(date(2026, 10, 2), date(2026, 10, 31))
    assert Period(None, TODAY).previous() is None
    assert november.contains(date(2026, 11, 30))
    assert not november.contains(date(2026, 10, 31))
    assert Period(None, TODAY).contains(date(2000, 1, 1))


# --- filters -----------------------------------------------------------------------------


def test_sent_means_applied_in_the_period() -> None:
    inside = apply(days_ago(3))
    apply(days_ago(40))  # before the period
    ApplicationFactory.create(stage=stage("Saved"))  # never applied
    assert list(last_30_days().sent()) == [inside]
    all_time = FilterContext(period=Period(None, TODAY), today=TODAY)
    assert all_time.sent().count() == 2


def test_dimension_filters() -> None:
    stepstone = SourceFactory.create(name="StepStone")
    match = apply(
        days_ago(1),
        source=stepstone,
        remote_type=RemoteType.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
    )
    Application.objects.filter(pk=match.pk).update(channel=Channel.EMAIL)
    apply(days_ago(1))  # Manual source, no work mode, no channel

    def count(**filters: Any) -> int:
        return last_30_days(**filters).sent().count()

    assert count() == 2
    assert count(sources=(stepstone.pk,)) == 1
    assert count(channels=(Channel.EMAIL,)) == 1
    assert count(remote_types=(RemoteType.REMOTE,)) == 1
    assert count(employment_types=(EmploymentType.FULL_TIME,)) == 1
    assert count(sources=(stepstone.pk,), channels=(Channel.REFERRAL,)) == 0


def test_tag_filter_counts_each_application_once() -> None:
    python, django = TagFactory.create(name="python"), TagFactory.create(name="django")
    application = apply(days_ago(1))
    application.tags.add(python, django)  # BOTH tags match the filter below
    apply(days_ago(1))
    assert last_30_days(tags=(python.pk, django.pk)).sent().count() == 1


def test_postings_ignore_application_only_filters() -> None:
    source = SourceFactory.create(name="LinkedIn")
    JobPostingFactory.create(source=source)
    JobPostingFactory.create()
    JobPostingFactory.create(
        remote_type=RemoteType.HYBRID, employment_type=EmploymentType.PART_TIME
    )
    assert last_30_days(sources=(source.pk,)).postings().count() == 1
    assert last_30_days(remote_types=(RemoteType.HYBRID,)).postings().count() == 1
    assert last_30_days(employment_types=(EmploymentType.PART_TIME,)).postings().count() == 1
    assert last_30_days(channels=(Channel.EMAIL,)).postings().count() == 3


# --- rates -------------------------------------------------------------------------------


def test_response_interview_and_offer_rates() -> None:
    screening = apply(days_ago(20))
    move(screening, "Screening", days_ago(15))
    interviewed = apply(days_ago(20))
    move(interviewed, "Interviewing", days_ago(10))
    offer_directly = apply(days_ago(20))
    move(offer_directly, "Offer", days_ago(5))  # no interview recorded: still counts
    rejected = apply(days_ago(20))
    close(rejected, "Rejected", days_ago(18))  # a rejection IS a response
    ghosted = apply(days_ago(20))
    close(ghosted, "Ghosted", days_ago(2))  # ghosted is NOT a response
    emailed = apply(days_ago(20))
    email_received(emailed, days_ago(12))
    apply(days_ago(20))  # no answer yet

    ctx = last_30_days()
    response = REGISTRY["response_rate"].compute(ctx)
    assert (response.numerator, response.denominator) == (5, 7)
    assert response.value == pytest.approx(5 / 7)
    assert REGISTRY["interview_rate"].compute(ctx).numerator == 2
    assert REGISTRY["offer_rate"].compute(ctx).numerator == 1


def test_reached_stages_count_even_after_moving_on() -> None:
    # Interviewing, then rejected: the interview still happened.
    application = apply(days_ago(20))
    move(application, "Interviewing", days_ago(10))
    close(application, "Rejected", days_ago(5))
    assert value("interview_rate", last_30_days()) == 1.0


def test_the_current_stage_counts_without_history() -> None:
    # Rows without a timeline (e.g. created directly) are judged by their stage.
    ApplicationFactory.create(stage=stage("Interviewing"), applied_on=days_ago(3))
    assert value("interview_rate", last_30_days()) == 1.0


def test_interview_role_follows_the_switch_not_the_name() -> None:
    PipelineStage.objects.filter(name="Interviewing").update(name="Gespräche")
    technical = PipelineStageFactory.create(name="Technical test", counts_as_interview=True)
    application = apply(days_ago(5))
    services.change_stage(application, technical, occurred_at=at(days_ago(2)))
    assert value("interview_rate", last_30_days()) == 1.0


def test_rejection_and_ghosting_rates() -> None:
    UserSettings.objects.update_or_create(pk=1, defaults={"ghosted_after_days": 14})
    rejected = apply(days_ago(25))
    close(rejected, "Rejected", days_ago(20))
    marked_ghosted = apply(days_ago(25))
    close(marked_ghosted, "Ghosted", days_ago(1))
    apply(days_ago(20))  # silent for 20 days > 14: counts as ghosted
    apply(days_ago(5))  # silent for 5 days: not yet
    answered = apply(days_ago(20))
    move(answered, "Screening", days_ago(19))  # answered, still open: not ghosted

    ctx = last_30_days()
    assert REGISTRY["rejection_rate"].compute(ctx).numerator == 1
    ghosting = REGISTRY["ghosting_rate"].compute(ctx)
    assert (ghosting.numerator, ghosting.denominator) == (2, 5)


def test_rates_without_applications_are_unknown_not_zero() -> None:
    result = REGISTRY["response_rate"].compute(last_30_days())
    assert result == MetricResult(None, Unit.PERCENT, 0, 0)


# --- durations ---------------------------------------------------------------------------


def test_days_to_first_response_and_to_offer() -> None:
    first = apply(days_ago(20))
    move(first, "Screening", days_ago(15))  # 5 days
    move(first, "Offer", days_ago(10))  # offer after 10 days
    second = apply(days_ago(20))
    email_received(second, days_ago(17))
    move(second, "Screening", days_ago(12))  # the FIRST answer counts: 3 days
    apply(days_ago(20))  # no answer: not part of the average

    ctx = last_30_days()
    response = REGISTRY["days_to_first_response"].compute(ctx)
    assert (response.value, response.numerator) == (4.0, 2)  # (5 + 3) / 2
    assert value("days_to_offer", ctx) == 10.0
    assert value("days_to_offer", FilterContext(period=Period(days_ago(5), TODAY))) is None


# --- snapshots ---------------------------------------------------------------------------


def test_active_pipeline_is_about_now() -> None:
    apply(days_ago(200))  # long ago, still open: counts
    in_progress = apply(days_ago(3))
    move(in_progress, "Screening", days_ago(1))
    closed = apply(days_ago(3))
    close(closed, "Rejected", days_ago(1))
    ApplicationFactory.create(stage=stage("Saved"))  # not sent yet
    comparison = compare("active_pipeline", last_30_days())
    assert comparison.current.value == 2
    assert comparison.previous is None  # a snapshot has no "previous period"


def test_follow_ups_due() -> None:
    due = apply(days_ago(10))
    Application.objects.filter(pk=due.pk).update(follow_up_on=days_ago(1))
    closed = apply(days_ago(10))
    close(closed, "Rejected", days_ago(2))
    Application.objects.filter(pk=closed.pk).update(follow_up_on=days_ago(1))  # closed: no
    TaskFactory.create(due_on=TODAY)  # unlinked task, due today
    TaskFactory.create(due_on=days_ago(1), done_at=timezone.now())  # done
    TaskFactory.create(due_on=TODAY + timedelta(days=3))  # not due yet
    TaskFactory.create(due_on=TODAY, application=due)  # linked, due

    assert value("follow_ups_due", last_30_days()) == 3
    other = SourceFactory.create(name="Elsewhere")
    # With a source filter, tasks of non-matching applications drop out (unlinked stay).
    assert value("follow_ups_due", last_30_days(sources=(other.pk,))) == 1


def test_inbox_backlog() -> None:
    JobPostingFactory.create_batch(2, triage_status=TriageStatus.NEW)
    JobPostingFactory.create(triage_status=TriageStatus.IGNORED)
    assert value("inbox_backlog", last_30_days()) == 2


# --- comparing with the previous period --------------------------------------------------


def test_compare_with_the_previous_period() -> None:
    apply(days_ago(2))
    apply(days_ago(3))
    apply(days_ago(40))  # in the previous 30 days
    comparison = compare("applications_sent", last_30_days())
    assert (comparison.current.value, comparison.previous.value) == (2, 1)  # type: ignore[union-attr]
    assert comparison.change == 1
    assert comparison.is_good is True


def test_higher_is_not_always_better() -> None:
    rejected = apply(days_ago(5))
    close(rejected, "Rejected", days_ago(1))
    previous = apply(days_ago(40))
    move(previous, "Screening", days_ago(35))
    comparison = compare("rejection_rate", last_30_days())
    assert comparison.change == 1.0  # from 0% to 100%
    assert comparison.is_good is False


def test_no_change_and_unknown_values() -> None:
    assert compare("applications_sent", last_30_days()).is_good is None  # 0 → 0
    unknown = compare("response_rate", last_30_days())
    assert unknown.change is None and unknown.is_good is None
    all_time = FilterContext(period=Period(None, TODAY))
    assert compare("applications_sent", all_time).previous is None


def test_registry() -> None:
    assert {"applications_sent", "response_rate", "ghosting_rate", "inbox_backlog"} <= set(REGISTRY)
    with pytest.raises(ValueError, match="already registered"):
        metrics.metric("applications_sent", "Again", Unit.COUNT, "")(metrics.applications_sent)


# --- goals -------------------------------------------------------------------------------


def test_weekly_goal_counts_this_calendar_week() -> None:
    monday = TODAY - timedelta(days=TODAY.weekday())
    apply(monday)
    apply(TODAY)
    apply(monday - timedelta(days=1))  # Sunday of last week: not this week
    Goal.objects.create(target=4, period=GoalPeriod.WEEK)
    Goal.objects.create(
        target=3, period=GoalPeriod.WEEK, metric="applications_sent", is_active=False
    )

    [progress] = goal_progress(last_30_days())  # the inactive goal is left out
    assert progress.done == 2  # (also when today IS Monday: then both are today)
    assert progress.period == Period(monday, TODAY)
    assert (progress.remaining, progress.ratio, progress.is_reached) == (2, 0.5, False)


def test_monthly_goal_and_reached_goals() -> None:
    apply(TODAY.replace(day=1))
    apply(TODAY)
    goal = Goal.objects.create(target=1, period=GoalPeriod.MONTH)
    [progress] = goal_progress(last_30_days())
    assert progress.done == 2
    assert (progress.remaining, progress.ratio, progress.is_reached) == (0, 1.0, True)
    assert str(goal) == "1 applications sent per month"


def test_only_one_active_goal_per_metric_and_period() -> None:
    Goal.objects.create(target=10)
    Goal.objects.create(target=8, is_active=False)  # old goals can stay as history
    with pytest.raises(IntegrityError):
        Goal.objects.create(target=12)


def test_goal_admin(admin_client: Client) -> None:
    Goal.objects.create(target=10)
    assert admin_client.get(reverse("admin:analytics_goal_changelist")).status_code == 200
