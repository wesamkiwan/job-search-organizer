"""Company and contact pages, and their selectors."""

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects

from organizer.applications.selectors import applications_for_company
from organizer.companies.models import Company, Contact, ContactKind
from organizer.companies.selectors import company_list, contact_list
from organizer.jobs.models import JobPosting
from tests.factories import ApplicationFactory, CompanyFactory, ContactFactory, stage

pytestmark = pytest.mark.django_db


# --- models / selectors ----------------------------------------------------------------


# "new" is a page name (/companies/new/), so a company called "New" can't get that slug.
def test_reserved_slug() -> None:
    assert CompanyFactory.create(name="New").slug == "new-2"


# Two counts over two relations: without distinct=True both would be 3 x 2 = 6.
def test_company_list_counts_are_not_multiplied() -> None:
    acme = CompanyFactory.create(name="Acme")
    ApplicationFactory.create_batch(2, posting__company=acme)
    ApplicationFactory.create(posting__company=acme, stage=stage("Rejected"),
                              closed_at="2026-11-01T10:00:00+01:00")  # fmt: skip
    ContactFactory.create_batch(2, company=acme)

    company = company_list().get(pk=acme.pk)
    assert company.application_count == 3  # type: ignore[attr-defined]
    assert company.open_application_count == 2  # type: ignore[attr-defined]
    assert company.contact_count == 2  # type: ignore[attr-defined]


def test_company_list_search() -> None:
    CompanyFactory.create(name="Acme", headquarters="Hamburg")
    CompanyFactory.create(name="Globex", industry="Energy")
    assert [c.name for c in company_list("hamburg")] == ["Acme"]
    assert [c.name for c in company_list("ENERGY")] == ["Globex"]


def test_applications_for_company() -> None:
    acme = CompanyFactory.create()
    mine = ApplicationFactory.create(posting__company=acme)
    ApplicationFactory.create()  # another company
    assert list(applications_for_company(acme)) == [mine]


def test_contact_list_search_and_kind() -> None:
    acme = CompanyFactory.create(name="Acme")
    jana = ContactFactory.create(first_name="Jana", company=acme,
                                 kind=ContactKind.EXTERNAL_RECRUITER)  # fmt: skip
    ContactFactory.create(first_name="Bernd", kind=ContactKind.HIRING_MANAGER)
    assert list(contact_list("acme")) == [jana]
    assert list(contact_list(kind=ContactKind.EXTERNAL_RECRUITER)) == [jana]
    assert contact_list(kind="nonsense").count() == 2  # unknown kind → no filter


# --- company pages ---------------------------------------------------------------------


def test_company_list_page(admin_client: Client) -> None:
    CompanyFactory.create(name="Acme", is_recruiting_agency=True)
    response = admin_client.get(reverse("companies:list"))
    assertContains(response, "Acme")
    assertContains(response, "Agency")
    assertContains(response, 'aria-current="page"')  # the sidebar item is active


def test_company_list_empty_states(admin_client: Client) -> None:
    url = reverse("companies:list")
    assertContains(admin_client.get(url), "No companies yet")
    CompanyFactory.create(name="Acme")
    assertContains(admin_client.get(url, {"q": "zzz"}), "No companies match")


def test_company_detail(admin_client: Client) -> None:
    acme = CompanyFactory.create(name="Acme & Co", rating=4, size="11-50")
    ApplicationFactory.create(posting__company=acme, posting__title="Backend Developer")
    ContactFactory.create(company=acme, first_name="Jana", last_name="Wendt")
    response = admin_client.get(acme.get_absolute_url())
    assertContains(response, "Backend Developer")
    assertContains(response, "Jana Wendt")
    assertContains(response, "4/5")
    # The "Add application" link carries the name, URL-encoded ("&" → %26).
    assertContains(response, "?company=Acme%20%26%20Co")


def test_company_detail_without_details(admin_client: Client) -> None:
    acme = CompanyFactory.create()
    assertContains(admin_client.get(acme.get_absolute_url()), "No details yet")


def test_create_company(admin_client: Client) -> None:
    response = admin_client.post(
        reverse("companies:create"), {"name": "Globex GmbH", "is_recruiting_agency": "on"}
    )
    company = Company.objects.get(name="Globex GmbH")
    assertRedirects(response, company.get_absolute_url())
    assert company.is_recruiting_agency


# The case-insensitive unique name (database constraint) shows as a form error.
def test_create_duplicate_company_shows_error(admin_client: Client) -> None:
    CompanyFactory.create(name="Acme")
    response = admin_client.post(reverse("companies:create"), {"name": "ACME"})
    assertContains(response, "A company with this name already exists.")


def test_company_form_renders_checkbox(admin_client: Client) -> None:
    response = admin_client.get(reverse("companies:create"))
    assertContains(response, 'type="checkbox"')
    assertContains(response, "Recruiting agency")


def test_edit_company(admin_client: Client) -> None:
    acme = CompanyFactory.create(name="Acme")
    url = reverse("companies:edit", args=[acme.slug])
    response = admin_client.post(url, {"name": "Acme Corp", "rating": "5"})
    assertRedirects(response, acme.get_absolute_url())  # slug unchanged
    acme.refresh_from_db()
    assert (acme.name, acme.rating) == ("Acme Corp", 5)
    assert admin_client.post(url, {"name": ""}).status_code == 200  # errors → form again


def test_delete_company_keeps_postings_and_contacts(admin_client: Client) -> None:
    acme = CompanyFactory.create(name="Acme")
    application = ApplicationFactory.create(posting__company=acme, posting__company_name_raw="Acme")
    contact = ContactFactory.create(company=acme)
    response = admin_client.post(reverse("companies:delete", args=[acme.slug]), follow=True)
    assertContains(response, "Its job postings and contacts were kept.")
    assert not Company.objects.filter(pk=acme.pk).exists()
    posting = JobPosting.objects.get(pk=application.posting.pk)
    assert posting.company is None
    assert posting.company_display == "Acme"
    assert Contact.objects.get(pk=contact.pk).company is None


def test_unknown_company_is_404(admin_client: Client) -> None:
    assert admin_client.get(reverse("companies:detail", args=["nope"])).status_code == 404


# --- contact pages ---------------------------------------------------------------------


def test_contact_list_page(admin_client: Client) -> None:
    ContactFactory.create(first_name="Jana", email="jana@example.com")
    response = admin_client.get(reverse("contacts:list"))
    assertContains(response, "Jana")
    assertContains(response, "mailto:jana@example.com")


def test_contact_list_empty_states(admin_client: Client) -> None:
    url = reverse("contacts:list")
    assertContains(admin_client.get(url), "No contacts yet")
    ContactFactory.create()
    assertContains(admin_client.get(url, {"q": "zzz"}), "No contacts match")


def test_contact_detail_with_referral(admin_client: Client) -> None:
    jana = ContactFactory.create(first_name="Jana", notes="Met at a meetup")
    ApplicationFactory.create(referred_by=jana, posting__title="Backend Developer")
    response = admin_client.get(jana.get_absolute_url())
    assertContains(response, "Backend Developer")
    assertContains(response, "Met at a meetup")


def test_contact_detail_without_details(admin_client: Client) -> None:
    contact = ContactFactory.create(company=None)
    response = admin_client.get(contact.get_absolute_url())
    assertContains(response, "No details yet")
    assertContains(response, "None.")  # no referrals


# "Add contact" on a company page pre-selects that company.
def test_create_contact_preselects_company(admin_client: Client) -> None:
    acme = CompanyFactory.create()
    response = admin_client.get(reverse("contacts:create"), {"company": acme.pk})
    assert response.context["form"]["company"].value() == str(acme.pk)


def test_create_contact(admin_client: Client) -> None:
    data = {"first_name": "Jana", "last_name": "Wendt", "kind": "external_recruiter"}
    response = admin_client.post(reverse("contacts:create"), data)
    contact = Contact.objects.get(first_name="Jana")
    assertRedirects(response, contact.get_absolute_url())


def test_edit_contact(admin_client: Client) -> None:
    contact = ContactFactory.create()
    url = reverse("contacts:edit", args=[contact.pk])
    response = admin_client.post(url, {"first_name": "Anna", "kind": "employee"})
    assertRedirects(response, contact.get_absolute_url())
    contact.refresh_from_db()
    assert contact.first_name == "Anna"
    assert admin_client.post(url, {"first_name": ""}).status_code == 200


def test_delete_contact_keeps_referred_application(admin_client: Client) -> None:
    contact = ContactFactory.create()
    application = ApplicationFactory.create(referred_by=contact)
    admin_client.post(reverse("contacts:delete", args=[contact.pk]))
    application.refresh_from_db()
    assert application.referred_by is None


# --- link from a company page to "Add application" -------------------------------------


def test_add_application_prefills_company(admin_client: Client) -> None:
    response = admin_client.get(reverse("applications:create"), {"company": "Acme & Co"})
    assert response.context["posting_form"]["company_name"].value() == "Acme & Co"
