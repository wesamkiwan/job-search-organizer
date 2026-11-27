"""The application list: selector (the query) and view (the page)."""

from datetime import date

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains, assertTemplateUsed

from organizer.applications.selectors import (
    ApplicationFilters,
    Status,
    application_cities,
    application_list,
)
from organizer.core.models import UserSettings
from tests.factories import (
    ApplicationFactory,
    CompanyFactory,
    JobPostingFactory,
    TagFactory,
    stage,
)

pytestmark = pytest.mark.django_db

LIST_URL = reverse("applications:list")


def titles(filters: ApplicationFilters) -> list[str]:
    return [a.posting.title for a in application_list(filters)]


# --- selector: filters ------------------------------------------------------------------


# Search looks in the title, the company (linked or raw name), the city and the notes.
@pytest.mark.parametrize("term", ["backend", "ACME", "Hamburg", "dream"])
def test_search_fields(term: str) -> None:
    ApplicationFactory.create(
        posting__title="Backend Developer",
        posting__company=CompanyFactory.create(name="Acme"),
        posting__city="Hamburg",
        notes="my dream job",
    )
    ApplicationFactory.create(posting__title="Other")
    assert titles(ApplicationFilters(search=term)) == ["Backend Developer"]


def test_search_finds_raw_company_name() -> None:
    ApplicationFactory.create(posting__company=None, posting__company_name_raw="Globex GmbH")
    assert len(titles(ApplicationFilters(search="globex"))) == 1


def test_filter_by_stage_and_priority() -> None:
    ApplicationFactory.create(
        posting__title="screening-high", stage=stage("Screening"), priority="high"
    )
    ApplicationFactory.create(
        posting__title="screening-low", stage=stage("Screening"), priority="low"
    )
    ApplicationFactory.create(posting__title="applied-high", priority="high")
    filters = ApplicationFilters(stage=stage("Screening"), priority="high")
    assert titles(filters) == ["screening-high"]


# Status: open (default) / closed / archived / all.
def test_filter_by_status() -> None:
    ApplicationFactory.create(posting__title="open")
    ApplicationFactory.create(posting__title="closed", closed_at=timezone.now())
    ApplicationFactory.create(posting__title="archived", is_archived=True)

    assert titles(ApplicationFilters()) == ["open"]
    assert titles(ApplicationFilters(status=Status.CLOSED)) == ["closed"]
    assert titles(ApplicationFilters(status=Status.ARCHIVED)) == ["archived"]
    assert sorted(titles(ApplicationFilters(status=Status.ALL))) == ["archived", "closed", "open"]


# Location: exact city (ignoring case); work mode: on-site / hybrid / remote.
def test_filter_by_city_and_remote_type() -> None:
    ApplicationFactory.create(
        posting__title="hh-remote", posting__city="Hamburg", posting__remote_type="remote"
    )
    ApplicationFactory.create(
        posting__title="hh-onsite", posting__city="Hamburg", posting__remote_type="on_site"
    )
    ApplicationFactory.create(posting__title="berlin", posting__city="Berlin")
    assert sorted(titles(ApplicationFilters(city="hamburg"))) == ["hh-onsite", "hh-remote"]
    assert titles(ApplicationFilters(city="Hamburg", remote_type="remote")) == ["hh-remote"]


# The Location dropdown lists each city once, A to Z, only for postings with an application.
def test_application_cities() -> None:
    ApplicationFactory.create(posting__city="Köln")
    ApplicationFactory.create(posting__city="Berlin")
    ApplicationFactory.create(posting__city="Berlin")
    ApplicationFactory.create(posting__city="")
    JobPostingFactory.create(city="München")  # no application → not in the list
    assert application_cities() == ["Berlin", "Köln"]


# --- selector: sorting -----------------------------------------------------------------


def test_sort_by_applied_date_empty_last_both_ways() -> None:
    ApplicationFactory.create(posting__title="none", applied_on=None)
    ApplicationFactory.create(posting__title="old", applied_on=date(2026, 1, 1))
    ApplicationFactory.create(posting__title="new", applied_on=date(2026, 6, 1))
    assert titles(ApplicationFilters(sort="applied")) == ["old", "new", "none"]
    assert titles(ApplicationFilters(sort="-applied")) == ["new", "old", "none"]


# Company sorting uses the linked name or, without a link, the raw name; ignoring case.
def test_sort_by_company() -> None:
    ApplicationFactory.create(
        posting__title="b", posting__company=CompanyFactory.create(name="beta")
    )
    ApplicationFactory.create(
        posting__title="a", posting__company=None, posting__company_name_raw="Alpha"
    )
    ApplicationFactory.create(
        posting__title="c", posting__company=CompanyFactory.create(name="Ceta")
    )
    assert titles(ApplicationFilters(sort="company")) == ["a", "b", "c"]


def test_sort_by_stage_uses_stage_order() -> None:
    ApplicationFactory.create(posting__title="offer", stage=stage("Offer"))
    ApplicationFactory.create(posting__title="saved", stage=stage("Saved"))
    assert titles(ApplicationFilters(sort="stage")) == ["saved", "offer"]


def test_sort_by_salary_expectation_empty_last() -> None:
    ApplicationFactory.create(posting__title="none")
    ApplicationFactory.create(posting__title="low", salary_expectation=55_000)
    ApplicationFactory.create(posting__title="high", salary_expectation=75_000)
    assert titles(ApplicationFilters(sort="-salary")) == ["high", "low", "none"]


# A sort value that isn't in the whitelist falls back to the default (no error).
def test_unknown_sort_falls_back_to_default() -> None:
    ApplicationFactory.create_batch(2)
    assert len(titles(ApplicationFilters(sort="posting__description_text; DROP TABLE"))) == 2


# --- view ------------------------------------------------------------------------------


def test_list_requires_login(client: Client) -> None:
    assert client.get(LIST_URL).status_code == 302


def test_list_page_shows_applications(admin_client: Client) -> None:
    ApplicationFactory.create(
        posting__title="Backend Developer",
        tags=[TagFactory.create(name="remote")],
        priority="high",
    )
    response = admin_client.get(LIST_URL)
    assertTemplateUsed(response, "applications/application_list.html")
    assertContains(response, "Backend Developer")
    assertContains(response, "remote")
    assertContains(response, "High priority")
    assertContains(response, "1 application")
    # The sidebar link is active on this page.
    assertContains(response, f'href="{LIST_URL}" aria-current="page"')


# The Salary column: your expectation, and the range from the ad below it.
def test_list_shows_salary_expectation_and_ad_range(admin_client: Client) -> None:
    ApplicationFactory.create(
        salary_expectation=65_000, posting__salary_min=55_000, posting__salary_max=70_000
    )
    response = admin_client.get(LIST_URL)
    assertContains(response, "65,000 EUR")
    assertContains(response, "Ad: 55,000-70,000 EUR per year")


# The URL's query string drives the filters (bookmarkable).
def test_list_filters_from_query_string(admin_client: Client) -> None:
    ApplicationFactory.create(posting__title="Backend Developer")
    ApplicationFactory.create(posting__title="Data Analyst")
    response = admin_client.get(LIST_URL, {"q": "backend"})
    assertContains(response, "Backend Developer")
    assertNotContains(response, "Data Analyst")


# The Location dropdown offers the cities, and choosing one filters the list.
def test_location_filter_on_page(admin_client: Client) -> None:
    ApplicationFactory.create(posting__title="In Hamburg", posting__city="Hamburg")
    ApplicationFactory.create(posting__title="In Berlin", posting__city="Berlin")
    response = admin_client.get(LIST_URL, {"city": "Hamburg"})
    assertContains(response, '<option value="Berlin"')  # still offered in the dropdown
    assertContains(response, "In Hamburg")
    assertNotContains(response, "In Berlin")


# Nonsense in a hand-edited URL is ignored instead of crashing the page.
def test_invalid_query_values_are_ignored(admin_client: Client) -> None:
    ApplicationFactory.create(posting__title="Backend Developer")
    response = admin_client.get(
        LIST_URL, {"stage": "999999", "status": "nope", "page": "abc", "city": "Atlantis"}
    )
    assert response.status_code == 200
    assertContains(response, "Backend Developer")


# An HTMX request gets only the results fragment, and the response says it varies by that.
def test_htmx_request_returns_only_results(admin_client: Client) -> None:
    ApplicationFactory.create(posting__title="Backend Developer")
    response = admin_client.get(LIST_URL, {"q": "backend"}, headers={"HX-Request": "true"})
    assertTemplateUsed(response, "applications/partials/application_results.html")
    assertNotContains(response, "<html")
    assertContains(response, "Backend Developer")
    assert "HX-Request" in response["Vary"]


def test_empty_states(admin_client: Client) -> None:
    assertContains(admin_client.get(LIST_URL), "No applications yet")
    ApplicationFactory.create()
    assertContains(admin_client.get(LIST_URL, {"q": "nothing-matches"}), "No applications match")


def test_pagination(admin_client: Client) -> None:
    ApplicationFactory.create_batch(26)  # PAGE_SIZE is 25
    first = admin_client.get(LIST_URL)
    assertContains(first, "Page 1 of 2")
    assertContains(first, "page=2")
    second = admin_client.get(LIST_URL, {"page": 2})
    assert len(second.context["page"].object_list) == 1


# Sort links toggle the direction and keep the other filters.
def test_sort_header_links(admin_client: Client) -> None:
    ApplicationFactory.create()
    response = admin_client.get(LIST_URL, {"q": "dev", "sort": "title"})
    assertContains(response, 'aria-sort="ascending"')
    assertContains(response, "?q=dev&amp;sort=-title")  # next click: descending, search kept


# No N+1: the number of queries is the same for 3 rows and for 13 rows.
def test_query_count_does_not_grow_with_rows(admin_client: Client) -> None:
    def count_queries() -> int:
        # CaptureQueriesContext records every SQL query run inside the "with" block.
        with CaptureQueriesContext(connection) as captured:
            admin_client.get(LIST_URL)
        return len(captured.captured_queries)

    # Create the settings row first: the very first request would create it (3 extra
    # queries), which has nothing to do with the number of rows.
    UserSettings.load()
    tag = TagFactory.create()
    ApplicationFactory.create_batch(3, tags=[tag])
    few = count_queries()
    ApplicationFactory.create_batch(10, tags=[tag])
    assert count_queries() == few
