"""Customizable layout, CSV export and caching of the dashboard (Phase 3, batch D)."""

import csv
import io
import json
from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.sessions.models import Session
from django.core.cache import cache as django_cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains, assertRedirects

from organizer.analytics import cache, layout
from organizer.analytics.filters import FilterContext, Period
from organizer.analytics.models import DashboardLayout, Goal
from organizer.analytics.views import safe_cell
from organizer.analytics.widgets import DEFAULT_LAYOUT, WIDGETS, Links
from tests.factories import ApplicationFactory, JobPostingFactory

pytestmark = pytest.mark.django_db


def keys() -> list[str]:
    return [p.key for p in layout.placements()]


# --- layout rules ------------------------------------------------------------------------


def test_default_layout_shows_every_widget_once() -> None:
    assert keys()[: len(DEFAULT_LAYOUT)] == list(DEFAULT_LAYOUT)
    assert sorted(keys()) == sorted(WIDGETS)
    assert layout.hidden_widgets() == []
    assert layout.placements()[0].size == WIDGETS[DEFAULT_LAYOUT[0]].size


def test_saved_order_and_sizes() -> None:
    layout.save([{"key": "funnel", "size": "full"}, {"key": "kpis", "size": "half"}])
    assert keys() == ["funnel", "kpis"]  # everything else was hidden by the save
    assert [p.size for p in layout.placements()] == ["full", "half"]
    assert "goal" in layout.hidden_widgets()


def test_invalid_stored_entries_are_ignored() -> None:
    # As if someone edited the JSON in the admin, or a widget was removed from the code.
    DashboardLayout.objects.create(
        widgets=[
            {"key": "gone", "size": "full"},
            {"key": "kpis", "size": "huge"},
            {"key": "kpis", "size": "half"},  # duplicate
            "nonsense",
        ],
        hidden=["funnel", 7],
    )
    placements = layout.placements()
    assert placements[0] == layout.Placement("kpis", WIDGETS["kpis"].size)  # size fixed
    assert keys().count("kpis") == 1
    assert "funnel" not in keys() and "gone" not in keys()
    # New widgets (in neither list) are added at the end, so they don't stay invisible.
    assert "weekly" in keys()


def test_a_broken_widgets_value_is_survived() -> None:
    DashboardLayout.objects.create(widgets={"not": "a list"})
    assert sorted(keys()) == sorted(WIDGETS)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "Expected a list"),
        (["kpis"], "must be an object"),
        ([{"key": "nope", "size": "half"}], "Unknown widget"),
        ([{"key": "kpis", "size": "huge"}], "Unknown size"),
        ([{"key": "kpis", "size": "half"}, {"key": "kpis", "size": "full"}], "appears twice"),
    ],
)
def test_invalid_layouts_are_refused_as_a_whole(payload: Any, message: str) -> None:
    layout.save([{"key": "funnel", "size": "half"}])
    with pytest.raises(layout.LayoutError, match=message):
        layout.save(payload)
    assert keys() == ["funnel"]  # unchanged


def test_show_and_reset() -> None:
    layout.save([{"key": "funnel", "size": "half"}])
    layout.show("goal")
    layout.show("goal")  # already shown: nothing changes
    assert keys() == ["funnel", "goal"]
    with pytest.raises(layout.LayoutError):
        layout.show("nope")
    layout.reset()
    assert keys()[: len(DEFAULT_LAYOUT)] == list(DEFAULT_LAYOUT)


# --- layout views ------------------------------------------------------------------------


def post_json(client: Client, data: Any) -> Any:
    return client.post(
        reverse("analytics:layout_save"),
        data=json.dumps(data) if not isinstance(data, str) else data,
        content_type="application/json",
    )


def test_layout_save_view(admin_client: Client) -> None:
    response = post_json(admin_client, {"widgets": [{"key": "outcomes", "size": "full"}]})
    assert response.json() == {"message": "Layout saved."}
    assert keys() == ["outcomes"]


@pytest.mark.parametrize("body", ["{not json", json.dumps([1, 2]), json.dumps({"widgets": 3})])
def test_layout_save_view_refuses_bad_requests(admin_client: Client, body: str) -> None:
    response = post_json(admin_client, body)
    assert response.status_code == 400
    assert "error" in response.json()


def test_layout_save_needs_post(admin_client: Client) -> None:
    assert admin_client.get(reverse("analytics:layout_save")).status_code == 405


def test_dashboard_follows_the_layout(admin_client: Client) -> None:
    layout.save([{"key": "outcomes", "size": "full"}, {"key": "funnel", "size": "half"}])
    response = admin_client.get("/")
    html = response.content.decode()
    assert html.index('data-widget="outcomes"') < html.index('data-widget="funnel"')
    assertContains(response, 'data-widget="outcomes" data-size="full"')
    assertNotContains(response, 'data-widget="kpis"')
    assertContains(response, "Add a widget:")  # the hidden ones can be added back
    assertContains(response, 'name="key" value="kpis"')


def test_add_back_and_reset_views(admin_client: Client) -> None:
    layout.save([{"key": "funnel", "size": "half"}])
    response = admin_client.post(
        reverse("analytics:layout_show"), {"key": "kpis", "query": "range=7d"}
    )
    assertRedirects(response, "/?range=7d")
    assert keys() == ["funnel", "kpis"]
    response = admin_client.post(reverse("analytics:layout_show"), {"key": "nope"}, follow=True)
    assertContains(response, "Unknown widget")
    response = admin_client.post(reverse("analytics:layout_reset"), follow=True)
    assertContains(response, "back to its default layout")
    assert keys()[0] == DEFAULT_LAYOUT[0]


def test_empty_dashboard(admin_client: Client) -> None:
    layout.save([])
    assertContains(admin_client.get("/"), "No widgets on the dashboard")


def test_layout_admin(admin_client: Client) -> None:
    layout.current()
    response = admin_client.get(reverse("admin:analytics_dashboardlayout_changelist"))
    assertContains(response, "Default")


# --- CSV export ----------------------------------------------------------------------------


def read_csv(response: Any) -> list[list[str]]:
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # the byte order mark for Excel
    return list(csv.reader(io.StringIO(text[1:]), delimiter=";"))


def test_export_a_widget_as_csv(admin_client: Client) -> None:
    ApplicationFactory.create(applied_on=timezone.localdate())
    response = admin_client.get(reverse("analytics:export", args=["funnel"]), {"range": "7d"})
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    today = timezone.localdate()
    assert f'filename="dashboard-funnel-{today:%Y-%m-%d}.csv"' in response["Content-Disposition"]
    rows = read_csv(response)
    assert rows[0] == ["Step", "Applications", "Share of sent"]
    assert rows[1] == ["Applications sent", "1", "100%"]


def test_csv_cells_cannot_become_formulas(admin_client: Client) -> None:
    posting = JobPostingFactory.create(title='=HYPERLINK("http://evil")', salary_min=50000)
    ApplicationFactory.create(posting=posting, applied_on=timezone.localdate())
    rows = read_csv(admin_client.get(reverse("analytics:export", args=["salary"])))
    assert rows[1][0].startswith("'=HYPERLINK")


@pytest.mark.parametrize(
    ("value", "safe"),
    [
        ("=1+1", "'=1+1"),
        ("+5 pts", "'+5 pts"),
        ("-3", "'-3"),
        ("@SUM", "'@SUM"),
        ("67%", "67%"),
        ("", ""),
    ],
)
def test_safe_cell(value: str, safe: str) -> None:
    assert safe_cell(value) == safe


def test_export_unknown_widget(admin_client: Client) -> None:
    assert admin_client.get(reverse("analytics:export", args=["nope"])).status_code == 404


def test_table_view_offers_the_download(admin_client: Client) -> None:
    ApplicationFactory.create(applied_on=timezone.localdate())
    response = admin_client.get("/", {"range": "7d"})
    assertContains(response, f"{reverse('analytics:export', args=['funnel'])}?range=7d")


# --- caching -------------------------------------------------------------------------------


def test_widget_data_is_cached(django_assert_num_queries: Callable[..., Any]) -> None:
    ctx = FilterContext(period=Period(None, timezone.localdate()))
    first = cache.build(WIDGETS["funnel"], ctx, Links())
    with django_assert_num_queries(0):  # the second time: straight from the cache
        assert cache.build(WIDGETS["funnel"], ctx, Links()) == first


def test_saving_data_makes_the_cache_outdated() -> None:
    ctx = FilterContext(period=Period(None, timezone.localdate()))
    before = cache.build(WIDGETS["funnel"], ctx, Links())
    version = cache.data_version()
    ApplicationFactory.create(applied_on=timezone.localdate())  # post_save → bump
    assert cache.data_version() > version
    after = cache.build(WIDGETS["funnel"], ctx, Links())
    assert after["table"].rows[0][1] == "1" != before["table"].rows[0][1]


def test_other_filters_have_their_own_cache_entry() -> None:
    ApplicationFactory.create(applied_on=timezone.localdate())
    today = timezone.localdate()
    everything = cache.build(WIDGETS["funnel"], FilterContext(period=Period(None, today)), Links())
    by_channel = cache.build(
        WIDGETS["funnel"], FilterContext(period=Period(None, today), channels=("email",)), Links()
    )
    assert everything["table"].rows[0][1] == "1" and by_channel["table"].rows[0][1] == "0"


def test_unrelated_saves_dont_bump_the_version() -> None:
    version = cache.data_version()
    Session.objects.create(session_key="x" * 32, session_data="", expire_date=timezone.now())
    assert cache.data_version() == version


def test_bump_survives_a_missing_version_key() -> None:
    django_cache.delete(cache.VERSION_KEY)  # e.g. evicted from a full cache
    # ONE save (an ApplicationFactory would save company, source, posting and application:
    # four bumps). The first bump after the key went missing sets it to 2.
    Goal.objects.create(target=1)
    assert cache.data_version() == 2
