"""The dashboard page: filter form, widgets, drill-down and goals (Phase 3, batch B)."""

from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from django.http import QueryDict
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from organizer.analytics import widgets
from organizer.analytics.filters import FilterContext, Period, Preset, period_for
from organizer.analytics.forms import DashboardFilterForm, describe
from organizer.analytics.metrics import GROUPS, REGISTRY, MetricResult, Unit
from organizer.analytics.models import Goal, GoalPeriod
from organizer.analytics.widgets import WIDGETS, Links
from organizer.applications import services
from organizer.applications.models import Application, Channel
from tests.factories import ApplicationFactory, JobPostingFactory, SourceFactory, TagFactory, stage

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def days_ago(n: int) -> date:
    return TODAY - timedelta(days=n)


def at(day: date) -> datetime:
    return min(timezone.make_aware(datetime.combine(day, time(10))), timezone.now())


def apply(on: date, **posting: object) -> Application:
    application = ApplicationFactory.build(
        posting=JobPostingFactory.create(**posting), stage=stage("Applied")
    )
    return services.create_application(application, occurred_at=at(on))


def last_30_days(**filters: Any) -> FilterContext:
    return FilterContext(
        period=period_for(Preset.LAST_30_DAYS, today=TODAY), today=TODAY, **filters
    )


def build(key: str, ctx: FilterContext | None = None) -> dict[str, Any]:
    return WIDGETS[key].build(ctx or last_30_days(), Links({"range": "30d"}))


# --- the filter form ---------------------------------------------------------------------


def test_filter_form_defaults_to_the_last_30_days() -> None:
    form = DashboardFilterForm(QueryDict(""))
    ctx = form.context(today=TODAY)
    assert ctx.period == period_for(Preset.LAST_30_DAYS, today=TODAY)
    assert form.query() == {}
    assert not form.has_filters


def test_filter_form_reads_every_filter() -> None:
    source, tag = SourceFactory.create(name="StepStone"), TagFactory.create(name="python")
    form = DashboardFilterForm(
        QueryDict(
            f"range=custom&start=2026-10-01&end=2026-10-31&source={source.pk}&channel=email"
            f"&tag={tag.pk}&remote_type=remote&employment_type=full_time"
        )
    )
    ctx = form.context(today=TODAY)
    assert ctx.period == Period(date(2026, 10, 1), date(2026, 10, 31))
    assert (ctx.sources, ctx.channels, ctx.tags) == ((source.pk,), ("email",), (tag.pk,))
    assert (ctx.remote_types, ctx.employment_types) == (("remote",), ("full_time",))
    assert form.query()["start"] == "2026-10-01"
    assert form.query()["source"] == str(source.pk)
    assert form.has_filters


def test_invalid_filter_values_are_ignored() -> None:
    form = DashboardFilterForm(QueryDict("range=forever&source=999&channel=pigeon&start=nope"))
    ctx = form.context()
    assert ctx.sources == () and ctx.channels == ()
    assert ctx.period.days == 30
    assert form.query() == {}


def test_describe_period() -> None:
    assert (
        describe(Period(date(2026, 11, 1), date(2026, 11, 28))) == "01 Nov 2026 \u2013 28 Nov 2026"
    )
    assert describe(Period(None, date(2026, 11, 28))) == "Until 28 Nov 2026"


# --- formatting --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("result", "text"),
    [
        (MetricResult(None, Unit.PERCENT), "—"),
        (MetricResult(0.666, Unit.PERCENT), "67%"),
        (MetricResult(4.5, Unit.DAYS), "4.5 d"),
        (MetricResult(1234, Unit.COUNT), "1,234"),
    ],
)
def test_format_value(result: MetricResult, text: str) -> None:
    assert widgets.format_value(result) == text


@pytest.mark.parametrize(
    ("unit", "change", "text"),
    [
        (Unit.PERCENT, 0.05, "+5 pts"),  # percentage POINTS
        (Unit.DAYS, -3.5, "\u22123.5 d"),  # a real minus sign
        (Unit.COUNT, 6, "+6"),
    ],
)
def test_format_change(unit: str, change: float, text: str) -> None:
    assert widgets.format_change(unit, change) == text


def test_links_keep_the_filters() -> None:
    links = Links({"range": "90d", "source": "3"})
    assert links.group("responded") == (
        f"{reverse('analytics:drilldown')}?range=90d&source=3&group=responded"
    )
    week = Period(date(2026, 11, 23), date(2026, 11, 29))
    url = links.period("sent", week)
    # The week replaces the period; the other filters stay.
    for part in ("range=custom", "source=3", "start=2026-11-23", "end=2026-11-29", "group=sent"):
        assert part in url
    assert "start=&" in links.period("sent", Period(None, date(2026, 11, 29)))


# --- widgets -----------------------------------------------------------------------------


def test_kpi_tiles() -> None:
    answered = apply(days_ago(5))
    services.change_stage(answered, stage("Screening"), occurred_at=at(days_ago(2)))
    apply(days_ago(5))
    apply(days_ago(40))  # previous period
    tiles = {t.label: t for t in build("kpis")["tiles"]}

    sent = tiles["Applications sent"]
    assert (sent.value, sent.change, sent.direction, sent.is_good) == ("2", "+1", "up", True)
    assert sent.url.startswith(reverse("analytics:drilldown"))
    assert tiles["Response rate"].detail == "1 of 2"
    assert tiles["Active pipeline"].detail == "right now"
    assert tiles["Days to first response"].detail == "average of 1"
    # The application from 40 days ago never got an answer: in the PREVIOUS period it
    # counts as ghosted (100%), now nothing is (0%). Fewer ghosted = good news.
    ghosting = tiles["Ghosting rate"]
    assert (ghosting.change, ghosting.direction, ghosting.is_good) == (
        "\u2212100 pts",
        "down",
        True,
    )


def test_kpi_tile_without_group_has_no_link(monkeypatch: pytest.MonkeyPatch) -> None:
    metric = REGISTRY["inbox_backlog"]
    tile = widgets.tile(metric.key, last_30_days(), Links())
    assert (tile.url, tile.detail) == ("", "right now")
    # A count metric WITH a previous period and no change shows no detail.
    assert widgets.tile("applications_sent", last_30_days(), Links()).detail == ""


def test_funnel() -> None:
    interviewed = apply(days_ago(10))
    services.change_stage(interviewed, stage("Interviewing"), occurred_at=at(days_ago(5)))
    apply(days_ago(10))
    bars = build("funnel")["bars"]
    assert [(b.label, b.value) for b in bars] == [
        ("Applications sent", 2),
        ("Got a response", 1),
        ("Got an interview", 1),
        ("Got an offer", 0),
    ]
    assert bars[1].note == "50% of sent"
    assert bars[0].share == 1.0 and bars[3].share == 0


def test_funnel_without_applications() -> None:
    data = build("funnel")
    assert data["bars"] == []
    assert data["table"].rows[0] == ("Applications sent", "0", "100%")


def test_weekly_columns_and_goal_line() -> None:
    monday = TODAY - timedelta(days=TODAY.weekday())
    apply(monday)
    apply(monday)
    apply(monday - timedelta(days=7))
    Goal.objects.create(target=4, period=GoalPeriod.WEEK)
    data = build("weekly")
    columns = data["columns"]
    assert len(columns) in (5, 6)  # 30 days touch 5 or 6 calendar weeks
    assert (columns[-1].value, columns[-2].value) == (2, 1)
    assert data["goal_target"] == 4
    assert data["goal_share"] == 1.0  # the goal is the highest point
    assert columns[-1].share == 0.5
    assert "range=custom" in columns[-1].url
    assert data["show_values"] and data["label_every"] == 1


def test_weekly_for_all_time_starts_at_the_first_application() -> None:
    apply(days_ago(400))
    all_time = FilterContext(period=Period(None, TODAY), today=TODAY)
    data = build("weekly", all_time)
    assert len(data["columns"]) == widgets.MAX_WEEKS  # capped to the last 26 weeks
    assert not data["show_values"]
    assert data["label_every"] == 3
    assert data["goal_target"] == 0


def test_weekly_with_nothing_sent_shows_the_current_week() -> None:
    all_time = FilterContext(period=Period(None, TODAY), today=TODAY)
    assert len(build("weekly", all_time)["columns"]) == 1


def test_pipeline_counts_open_applications_by_stage() -> None:
    screening = apply(days_ago(3))
    services.change_stage(screening, stage("Screening"), occurred_at=at(days_ago(1)))
    apply(days_ago(100))  # old but still open: counts (it's about now)
    rejected = apply(days_ago(3))
    services.close_application(rejected, occurred_at=at(days_ago(1)))
    data = build("pipeline")
    counts = {b.label: b.value for b in data["bars"]}
    assert counts["Applied"] == 1 and counts["Screening"] == 1
    assert "Rejected" not in counts  # only open stages are listed
    assert f"stage={stage('Screening').pk}" in next(
        b.url for b in data["bars"] if b.label == "Screening"
    )


def test_pipeline_when_nothing_is_open() -> None:
    assert build("pipeline")["bars"] == []


def test_outcomes_split_sent_into_parts_that_add_up() -> None:
    apply(days_ago(2))  # waiting
    rejected = apply(days_ago(20))
    services.close_application(rejected, occurred_at=at(days_ago(10)))
    silent = apply(days_ago(29))  # no answer for 29 days (setting: 30) → still waiting
    assert silent
    data = build("outcomes")
    counts = {s.key: s.count for s in data["segments"]}
    assert counts == {"waiting": 2, "rejected": 1, "accepted": 0, "ghosted": 0, "withdrawn": 0}
    assert data["total"] == 3 == sum(counts.values())
    first = data["segments"][0]
    assert (first.slot, first.classes, first.swatch) == (
        1,
        "bg-chart-1 text-chart-on-fill",
        "bg-chart-1",
    )
    assert first.share_text == "67%" and first.fits_label
    assert data["segments"][3].classes == "bg-chart-4 text-chart-on-4"  # dark text on yellow


def test_silent_applications_move_from_waiting_to_ghosted() -> None:
    apply(days_ago(29))
    ctx = FilterContext(period=Period(None, TODAY), today=TODAY + timedelta(days=5))
    counts = {s.key: s.count for s in build("outcomes", ctx)["segments"]}
    assert (counts["waiting"], counts["ghosted"]) == (0, 1)


def test_goal_widget() -> None:
    assert build("goal")["progress"] == []
    Goal.objects.create(target=5)
    apply(TODAY)
    data = build("goal")
    assert data["progress"][0].done == 1
    assert "range=custom" in data["this_week_url"]
    assert data["table"].rows[0][1:] == ("1", "4", "20%")


def test_widget_registry_refuses_duplicates() -> None:
    with pytest.raises(ValueError, match="already registered"):
        widgets.widget("kpis", "Again", "", "kpis.html")(widgets.kpis)


# --- pages -------------------------------------------------------------------------------


def test_dashboard_page(admin_client: Client) -> None:
    apply(days_ago(3))
    response = admin_client.get(reverse("analytics:dashboard"))
    for title in ("Key numbers", "Goal", "Funnel", "Applications per week", "Outcomes"):
        assertContains(response, title)
    assertContains(response, "compared with")
    assertContains(response, "Show as table")
    assertContains(response, 'aria-current="page"')  # Dashboard in the sidebar


def test_dashboard_all_time_has_no_comparison(admin_client: Client) -> None:
    response = admin_client.get(reverse("analytics:dashboard"), {"range": "all"})
    assertContains(response, "Until ")
    assertNotContains(response, " · compared with")  # the period line (not the widget text)


def test_dashboard_filters_and_clear_link(admin_client: Client) -> None:
    source = SourceFactory.create(name="StepStone")
    apply(days_ago(3), source=source, title="Matching job")
    response = admin_client.get(
        reverse("analytics:dashboard"),
        {"range": "90d", "source": str(source.pk), "channel": Channel.EMAIL},
    )
    assertContains(response, "Clear filters")
    assertContains(response, 'href="/?range=90d"')
    assertContains(response, f"source={source.pk}")  # the links keep the filters


def test_drilldown_lists_the_applications_behind_a_number(admin_client: Client) -> None:
    answered = apply(days_ago(5), title="Answered job")
    services.change_stage(answered, stage("Screening"), occurred_at=at(days_ago(2)))
    apply(days_ago(5), title="Silent job")
    response = admin_client.get(reverse("analytics:drilldown"), {"group": "responded"})
    assertContains(response, "Got a response")
    assertContains(response, "Answered job")
    assertNotContains(response, "Silent job")
    assertContains(response, "1 application ·")
    assertContains(response, f'href="{reverse("analytics:dashboard")}"')


def test_drilldown_keeps_filters_in_the_back_link_and_paginates(admin_client: Client) -> None:
    for _ in range(51):
        ApplicationFactory.create(applied_on=days_ago(1))
    response = admin_client.get(reverse("analytics:drilldown"), {"group": "sent", "range": "7d"})
    assertContains(response, "Page 1 of 2")
    # {{ query }} is escaped (& → &amp;), the "&page=" written in the template is not.
    assertContains(response, "?range=7d&amp;group=sent&page=2")
    assertContains(response, 'href="/?range=7d"')
    response = admin_client.get(
        reverse("analytics:drilldown"), {"group": "sent", "range": "7d", "page": "2"}
    )
    assertContains(response, "Previous")


def test_drilldown_empty_and_unknown(admin_client: Client) -> None:
    assertContains(
        admin_client.get(reverse("analytics:drilldown"), {"group": "offered"}), "No applications"
    )
    assert admin_client.get(reverse("analytics:drilldown"), {"group": "x"}).status_code == 404


def test_every_group_can_be_drilled_into(admin_client: Client) -> None:
    for key in GROUPS:
        response = admin_client.get(reverse("analytics:drilldown"), {"group": key})
        assert response.status_code == 200, key


# --- goal actions ------------------------------------------------------------------------


def test_set_a_goal_keeps_the_old_one_as_history(admin_client: Client) -> None:
    old = Goal.objects.create(target=5)
    response = admin_client.post(
        reverse("analytics:goal_set"), {"target": 10, "period": "week", "query": "range=90d"}
    )
    assertRedirects(response, "/?range=90d")
    old.refresh_from_db()
    assert not old.is_active
    assert Goal.objects.get(is_active=True).target == 10


def test_invalid_goal_and_smuggled_query(admin_client: Client) -> None:
    response = admin_client.post(
        reverse("analytics:goal_set"),
        {"target": 0, "period": "week", "query": "next=https://evil.example&range=7d"},
        follow=True,
    )
    assertContains(response, "Applications: Ensure this value is greater than or equal to 1.")
    assert response.redirect_chain[0][0] == "/?range=7d"  # only known filters survive
    assert not Goal.objects.exists()


def test_remove_a_goal(admin_client: Client) -> None:
    goal = Goal.objects.create(target=5)
    response = admin_client.post(reverse("analytics:goal_stop", args=[goal.pk]), {})
    assertRedirects(response, "/")
    goal.refresh_from_db()
    assert not goal.is_active
    assert admin_client.post(reverse("analytics:goal_stop", args=[goal.pk])).status_code == 404


def test_goal_widget_on_the_page(admin_client: Client) -> None:
    assertContains(admin_client.get("/"), "No goal yet.")
    Goal.objects.create(target=3)
    response = admin_client.get("/")
    assertContains(response, "of 3 per week")
    assertContains(response, "Remove goal")
