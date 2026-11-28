"""The "what works?" widgets and the insights panel (Phase 3, batch C)."""

from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone
from pytest_django.asserts import assertContains

from organizer.analytics import insights, performance
from organizer.analytics.filters import FilterContext, Period, Preset, period_for
from organizer.analytics.models import Goal
from organizer.analytics.performance import MIN_SAMPLE, Row
from organizer.analytics.widgets import WIDGETS, Links
from organizer.applications import services
from organizer.applications.models import Application, Channel, RejectionReason
from organizer.core.models import UserSettings
from organizer.documents import services as document_services
from organizer.jobs.models import RemoteType, SalaryPeriod, Seniority
from tests.factories import (
    ApplicationFactory,
    DocumentFactory,
    DocumentVersionFactory,
    JobPostingFactory,
    SourceFactory,
    stage,
)

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def at(day: date, hour: int = 10) -> datetime:
    return min(timezone.make_aware(datetime.combine(day, time(hour))), timezone.now())


def apply(on: date, *, channel: str = "", **posting: Any) -> Application:
    application = ApplicationFactory.build(
        posting=JobPostingFactory.create(**posting), stage=stage("Applied"), channel=channel
    )
    return services.create_application(application, occurred_at=at(on))


def answer(application: Application, on: date, stage_name: str = "Screening") -> None:
    services.change_stage(application, stage(stage_name), occurred_at=at(on))


def last_30_days() -> FilterContext:
    return FilterContext(period=period_for(Preset.LAST_30_DAYS, today=TODAY), today=TODAY)


def build(key: str, ctx: FilterContext | None = None) -> dict[str, Any]:
    return WIDGETS[key].build(ctx or last_30_days(), Links({"range": "30d"}))


def rows(key: str) -> dict[str, Row]:
    data = build(key)
    return {row.label: row for section in data["sections"] for row in section["rows"]}


# --- performance tables ------------------------------------------------------------------


def test_performance_by_source() -> None:
    stepstone = SourceFactory.create(name="StepStone")
    for _ in range(MIN_SAMPLE):
        answer(apply(days_ago(10), source=stepstone), days_ago(5))
    apply(days_ago(10))  # Manual, no answer
    by_source = rows("sources")
    assert (by_source["StepStone"].sent, by_source["StepStone"].response_rate) == (5, 1.0)
    assert not by_source["StepStone"].few
    assert by_source["Manual"].few  # 1 application: "few data"
    assert f"source={stepstone.pk}" in by_source["StepStone"].url
    assert by_source["StepStone"].table_row() == ("StepStone", "5", "100%", "0%")


def test_performance_by_channel_names_unset_channels() -> None:
    apply(days_ago(3), channel=Channel.REFERRAL)
    apply(days_ago(3))
    by_channel = rows("channels")
    assert set(by_channel) == {"Referral", "Not set"}
    assert by_channel["Not set"].url == ""  # nothing to filter by
    assert "channel=referral" in by_channel["Referral"].url


def test_performance_tables_when_empty() -> None:
    data = build("sources")
    assert data["sections"] == [] and data["table"].rows == []


def test_performance_by_document_version() -> None:
    document = DocumentFactory.create(title="CV EN")
    v1 = DocumentVersionFactory.create(document=document)
    v2 = DocumentVersionFactory.create(document=document)
    for version, answered in ((v1, True), (v1, False), (v2, True)):
        application = apply(days_ago(8))
        if answered:
            answer(application, days_ago(4), "Interviewing")
        document_services.attach_version(application, version, sent_at=at(days_ago(8)))
    old = apply(days_ago(60))  # sent before the period: not counted
    document_services.attach_version(old, v2, sent_at=at(days_ago(60)))

    by_version = rows("documents")
    assert by_version["CV EN v1 (CV)"].sent == 2
    assert by_version["CV EN v1 (CV)"].interview_rate == 0.5
    assert by_version["CV EN v2 (CV)"].sent == 1


def test_performance_by_job_profile() -> None:
    apply(days_ago(5), remote_type=RemoteType.REMOTE, seniority=Seniority.SENIOR)
    apply(days_ago(5))
    data = build("profiles")
    titles = [section["title"] for section in data["sections"]]
    assert titles == ["Work mode", "Employment", "Seniority"]
    work_mode = {row.label: row for row in data["sections"][0]["rows"]}
    assert work_mode["Remote"].sent == 1 and "remote_type=remote" in work_mode["Remote"].url
    seniority = {row.label: row for row in data["sections"][2]["rows"]}
    assert seniority["Senior"].url == ""  # the dashboard has no seniority filter
    assert ("Work mode: Remote", "1", "0%", "0%") in data["table"].rows


# --- rejections, time in stage, weekday --------------------------------------------------


def test_rejections_by_stage_and_reason() -> None:
    early = apply(days_ago(20))
    services.close_application(
        early, reason=RejectionReason.SKILLS_MISMATCH, occurred_at=at(days_ago(15))
    )
    late = apply(days_ago(20))
    answer(late, days_ago(18), "Interviewing")
    services.close_application(late, occurred_at=at(days_ago(10)))
    data = build("rejections")
    assert data["total"] == 2
    assert {b.label: b.value for b in data["stages"]} == {"Applied": 1, "Interviewing": 1}
    assert {b.label for b in data["reasons"]} == {"Skills don't match", "Not recorded"}
    assert ("Reason", "Skills don't match", "1") in data["table"].rows


def test_rejections_when_none() -> None:
    assert build("rejections")["total"] == 0


def test_time_in_stage_counts_finished_stays_only() -> None:
    first = apply(days_ago(20))
    answer(first, days_ago(16))  # 4 days in Applied
    answer(first, days_ago(10), "Interviewing")  # 6 days in Screening
    services.close_application(first, occurred_at=at(days_ago(5)))  # 5 days interviewing
    second = apply(days_ago(12))
    answer(second, days_ago(10))  # 2 days in Applied; Screening still going on: left out
    data = build("time_in_stage")
    averages = {b.label: b.text for b in data["bars"]}
    assert averages == {"Applied": "3.0 d", "Screening": "6.0 d", "Interviewing": "5.0 d"}
    assert "Rejected" not in averages  # final stages are left out
    assert data["table"].rows[0] == ("Applied", "3.0 d", "2 moves")


def test_time_in_stage_without_moves() -> None:
    apply(days_ago(3))
    assert build("time_in_stage")["bars"] == []


def test_applications_by_weekday() -> None:
    monday = TODAY - timedelta(days=TODAY.weekday() + 7)  # Monday of last week
    answer(apply(monday), monday + timedelta(days=1))
    apply(monday)
    apply(monday + timedelta(days=2))  # Wednesday
    data = build("weekday")
    columns = {c.label: c for c in data["columns"]}
    assert (columns["Mon"].value, columns["Mon"].note) == (2, "50%")
    assert (columns["Wed"].value, columns["Wed"].note) == (1, "0%")
    assert columns["Sun"].note == "—"
    assert data["note_label"] == "answered"


def test_weekday_when_empty() -> None:
    assert build("weekday")["columns"] == []


# --- activity ----------------------------------------------------------------------------


def test_activity_heatmap_levels() -> None:
    busy = days_ago(3)
    for _ in range(5):
        apply(busy)  # 5 "created" events on one day
    apply(days_ago(4))  # 1 on another day
    data = build("activity")
    cells = {cell.day: cell for week in data["grid"] for cell in week}
    assert (cells[busy].count, cells[busy].level) == (5, 5)
    assert (cells[days_ago(4)].count, cells[days_ago(4)].level) == (1, 1)
    assert cells[days_ago(5)].classes == "bg-surface-muted"
    assert cells[busy].classes == "bg-chart-heat-5"
    assert data["total"] == 6
    # Days of the first week before the period starts are shown, but faded.
    first_cell = data["grid"][0][0]
    assert first_cell.in_period == (first_cell.day >= days_ago(29))


def test_activity_when_empty_and_all_time() -> None:
    assert build("activity")["total"] == 0
    apply(days_ago(100))
    all_time = FilterContext(period=Period(None, TODAY), today=TODAY)
    assert build("activity", all_time)["total"] == 1


# --- salaries ----------------------------------------------------------------------------


def test_salary_rows_use_yearly_amounts_in_the_default_currency() -> None:
    with_range = apply(days_ago(5), title="Backend", salary_min=60000, salary_max=70000)
    Application.objects.filter(pk=with_range.pk).update(salary_expectation=75000)
    apply(days_ago(5), title="Monthly", salary_min=5000, salary_max=6000,
          salary_period=SalaryPeriod.MONTH)  # fmt: skip
    apply(days_ago(5), title="Dollars", salary_min=90000, salary_currency="USD")
    apply(days_ago(5), title="No salary")

    data = build("salary")
    [row] = data["rows"]
    assert row.label.startswith("Backend · ")
    assert (row.low, row.high, row.expected) == (60000, 70000, 75000)
    assert (row.range_start, row.expected_at) == (0.0, 1.0)  # the scale is 60k .. 75k
    assert row.range_width == pytest.approx(10000 / 15000)
    assert (data["scale_min"], data["scale_max"]) == ("60,000 EUR", "75,000 EUR")
    assert data["median_advertised"] == "65,000 EUR"
    assert data["median_expected"] == "75,000 EUR"


def test_salary_with_only_an_expectation_or_only_a_minimum() -> None:
    expectation_only = apply(days_ago(5))
    Application.objects.filter(pk=expectation_only.pk).update(salary_expectation=50000)
    apply(days_ago(5), salary_min=55000)  # "from 55,000"
    data = build("salary")
    by_low = {row.low: row for row in data["rows"]}
    assert by_low[None].range_width == 0.0 and by_low[None].expected == 50000
    assert by_low[55000].range_width == 0.0  # a single amount: a dot-sized bar
    assert data["median_expected"] == "50,000 EUR"


def test_salary_expectation_in_another_currency_is_ignored() -> None:
    application = apply(days_ago(5), salary_min=60000, salary_max=60000)
    Application.objects.filter(pk=application.pk).update(
        salary_expectation=70000, salary_expectation_currency="CHF"
    )
    [row] = build("salary")["rows"]
    assert row.expected is None
    assert build("salary")["median_expected"] == "—"


def test_salary_when_empty() -> None:
    assert build("salary")["rows"] == []


# --- insights ----------------------------------------------------------------------------


def make_row(label: str, sent: int, responded: int) -> Row:
    return Row(label, sent, responded, responded)


def test_compare_rows_needs_enough_data_and_a_clear_difference() -> None:
    clear = [make_row("Referral", 5, 4), make_row("Portal", 10, 2)]
    insight = insights.compare_rows(clear, "response_rate", "response rate", "Channel")
    assert insight is not None
    assert insight.text.startswith("Channel “Referral” has 4.0\u00d7 higher response rate")
    assert "(80% vs 20%, from 5 and 10 applications)" in insight.text

    few = [make_row("Referral", 4, 4), make_row("Portal", 10, 2)]  # 4 < MIN_SAMPLE
    assert insights.compare_rows(few, "response_rate", "", "") is None
    close = [make_row("A", 10, 5), make_row("B", 10, 4)]  # 10 points... but only 1.25x
    assert insights.compare_rows(close, "response_rate", "", "") is None
    zero = [make_row("A", 5, 3), make_row("B", 5, 0)]
    assert "a clearly higher" in insights.compare_rows(zero, "response_rate", "rate", "X").text  # type: ignore[union-attr]


def test_silent_applications_insight() -> None:
    UserSettings.objects.update_or_create(pk=1, defaults={"ghosted_after_days": 14})
    apply(days_ago(20))
    apply(days_ago(40))  # outside the period, still counted: it's about now
    insight = insights.silent_applications(last_30_days(), Links())
    assert insight is not None
    assert insight.text.startswith("2 applications have had no response for 14+ days.")
    assert "range=all" in insight.url and "group=ghosted" in insight.url


def test_one_silent_application_reads_well() -> None:
    apply(days_ago(40))
    insight = insights.silent_applications(last_30_days(), Links())
    assert insight is not None and "1 application has had" in insight.text
    assert "close it as ghosted" in insight.text


def test_behind_the_weekly_goal() -> None:
    Goal.objects.create(target=3)
    apply(TODAY)
    insight = insights.behind_goal(last_30_days())
    assert insight is not None
    assert "2 applications behind this week's goal (1 of 3," in insight.text
    days_left = 6 - TODAY.weekday()
    assert (f"{days_left} days left" if days_left else "today is the last day") in insight.text


def test_no_goal_insight_when_reached_or_monthly() -> None:
    Goal.objects.create(target=1)
    Goal.objects.create(target=30, period="month")
    apply(TODAY)
    assert insights.behind_goal(last_30_days()) is None


def test_document_version_insight() -> None:
    document = DocumentFactory.create(title="CV")
    good, bad = DocumentVersionFactory.create_batch(2, document=document)
    for version, answered in ((good, 4), (bad, 1)):
        for n in range(MIN_SAMPLE):
            application = apply(days_ago(10))
            if n < answered:
                answer(application, days_ago(5))
            document_services.attach_version(application, version, sent_at=at(days_ago(10)))
    insight = insights.best_document_version(last_30_days())
    assert insight is not None
    assert "“CV v1 (CV)” has 4.0\u00d7 higher response rate than “CV v2 (CV)”" in insight.text


def test_insights_widget() -> None:
    data = build("insights")
    assert data["insights"] == [] and data["min_sample"] == MIN_SAMPLE
    Goal.objects.create(target=50)
    data = build("insights")
    assert [i.tone for i in data["insights"]] == ["warning"]
    assert data["table"].rows == [(data["insights"][0].text,)]


def test_channel_insight_in_the_panel() -> None:
    for _ in range(MIN_SAMPLE):
        answer(apply(days_ago(9), channel=Channel.REFERRAL), days_ago(3), "Interviewing")
        apply(days_ago(9), channel=Channel.EMAIL)
    texts = [i.text for i in insights.build_insights(last_30_days(), Links())]
    assert any(
        t.startswith("Channel “Referral” has a clearly higher interview rate") for t in texts
    )


# --- the page ----------------------------------------------------------------------------


def test_dashboard_shows_every_widget(admin_client: Client) -> None:
    document = DocumentFactory.create(title="CV EN")
    version = DocumentVersionFactory.create(document=document)
    application = apply(days_ago(6), salary_min=50000, salary_max=60000)
    answer(application, days_ago(2))
    services.close_application(apply(days_ago(6)), occurred_at=at(days_ago(1)))
    document_services.attach_version(application, version, sent_at=at(days_ago(6)))
    response = admin_client.get("/")
    for title in (
        "Insights",
        "Performance by document version",
        "Performance by source",
        "Performance by channel",
        "Performance by job profile",
        "Rejections",
        "Time in stage",
        "Applications by weekday",
        "Activity",
        "Salaries",
    ):
        assertContains(response, title)
    assertContains(response, "few data")
    assertContains(response, "Advertised range")
    assertContains(response, "Second row: share answered.")


def test_dashboard_with_nothing_yet(admin_client: Client) -> None:
    response = admin_client.get("/")
    assertContains(response, "Nothing stands out yet.")
    assertContains(response, "No documents recorded as sent for this period.")
    assertContains(response, "No activity in this period.")
    assert performance.MIN_SAMPLE == 5
