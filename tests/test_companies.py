import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from organizer.companies.models import Company, Contact, ContactKind
from tests.factories import CompanyFactory, ContactFactory

# Every test here uses the database.
pytestmark = pytest.mark.django_db


# --- Company: slug ---------------------------------------------------------------------


# The slug is made from the name automatically; umlauts become plain letters.
def test_slug_is_generated_from_name() -> None:
    company = CompanyFactory.create(name="Müller & Söhne GmbH")
    assert company.slug == "muller-sohne-gmbh"


# Two different names that give the same slug ("ab"): the second one gets "-2".
def test_slug_is_unique() -> None:
    first = CompanyFactory.create(name="A&B")
    second = CompanyFactory.create(name="AB")
    assert (first.slug, second.slug) == ("ab", "ab-2")


# Renaming a company keeps its slug, so links to it keep working.
def test_slug_does_not_change_on_rename() -> None:
    company = CompanyFactory.create(name="Old Name")
    company.name = "New Name"
    company.save()
    assert company.slug == "old-name"


# A name without any letters or digits still gets a valid slug.
def test_slug_fallback_for_symbol_only_name() -> None:
    assert CompanyFactory.create(name="???").slug == "company"


# --- Company: validation ---------------------------------------------------------------


# The database itself refuses a second company with the same name in other letter case.
def test_company_name_is_unique_ignoring_case() -> None:
    CompanyFactory.create(name="SAP")
    with pytest.raises(IntegrityError):
        CompanyFactory.create(name="sap")


# Forms (and the admin) show a friendly message instead of crashing: full_clean() runs
# all validation, including the database constraint, before saving.
def test_duplicate_name_gives_friendly_validation_error() -> None:
    CompanyFactory.create(name="SAP")
    with pytest.raises(ValidationError, match="A company with this name already exists"):
        Company(name="Sap").full_clean()


# Ratings go from 1 to 5; empty (not rated) is allowed.
@pytest.mark.parametrize(
    ("rating", "is_valid"), [(None, True), (1, True), (5, True), (0, False), (6, False)]
)
def test_rating_range(rating: int | None, is_valid: bool) -> None:
    company = Company(name="Acme", slug="acme", rating=rating)
    if is_valid:
        company.full_clean()
    else:
        with pytest.raises(ValidationError):
            company.full_clean()


# custom_data starts as an empty dict, and every company gets its OWN dict.
def test_custom_data_defaults_to_separate_empty_dicts() -> None:
    first, second = CompanyFactory.create(), CompanyFactory.create()
    first.custom_data["team_size"] = 8
    assert second.custom_data == {}


# --- Contact ---------------------------------------------------------------------------


def test_contact_full_name_and_str() -> None:
    contact = ContactFactory.create(first_name="Anna", last_name="")
    assert contact.full_name == "Anna"
    assert str(contact) == "Anna"


# related_name="contacts": from a company to its contacts.
def test_company_lists_its_contacts() -> None:
    company = CompanyFactory.create()
    anna = ContactFactory.create(company=company)
    ContactFactory.create()  # belongs to another company
    assert list(company.contacts.all()) == [anna]


# on_delete=SET_NULL: deleting a company keeps its contacts, without a company.
def test_deleting_company_keeps_contacts() -> None:
    contact = ContactFactory.create()
    contact.company.delete()  # type: ignore[union-attr]
    contact.refresh_from_db()
    assert contact.company is None


def test_contact_kind_defaults_to_other() -> None:
    assert ContactFactory.create().kind == ContactKind.OTHER


# --- Admin -----------------------------------------------------------------------------


# The company list shows each company with its number of contacts.
def test_company_admin_list_shows_contact_count(admin_client: Client) -> None:
    company = CompanyFactory.create(name="Acme")
    ContactFactory.create_batch(2, company=company)  # create_batch: several at once
    response = admin_client.get(reverse("admin:companies_company_changelist"))
    assert response.status_code == 200
    assert response.context["cl"].result_list[0]._contact_count == 2


# Admin search finds companies by name.
def test_company_admin_search(admin_client: Client) -> None:
    CompanyFactory.create(name="Acme")
    CompanyFactory.create(name="Globex")
    url = reverse("admin:companies_company_changelist")
    response = admin_client.get(url, {"q": "acm"})
    assertContains(response, "Acme")
    assertNotContains(response, "Globex")


# The company edit page loads, including the contacts inline.
def test_company_admin_change_page_loads(admin_client: Client) -> None:
    contact = ContactFactory.create(first_name="Anna")
    url = reverse("admin:companies_company_change", args=[contact.company.pk])  # type: ignore[union-attr]
    response = admin_client.get(url)
    assertContains(response, "Anna")


# Contact list: searching by company name works (company__name in search_fields).
def test_contact_admin_search_by_company(admin_client: Client) -> None:
    ContactFactory.create(first_name="Anna", company=CompanyFactory.create(name="Acme"))
    ContactFactory.create(first_name="Bernd", company=CompanyFactory.create(name="Globex"))
    response = admin_client.get(reverse("admin:companies_contact_changelist"), {"q": "acme"})
    assertContains(response, "Anna")
    assertNotContains(response, "Bernd")


# Contact add page loads (with the company autocomplete widget).
def test_contact_admin_add_page_loads(admin_client: Client) -> None:
    response = admin_client.get(reverse("admin:companies_contact_add"))
    assert response.status_code == 200


# A contact without a company is fine (e.g. a freelance headhunter).
def test_contact_without_company() -> None:
    contact = ContactFactory.create(company=None)
    assert Contact.objects.get(pk=contact.pk).company is None


# get_absolute_url points to the edit page (until the real pages exist in step 1.9).
def test_get_absolute_url_opens_the_object(admin_client: Client) -> None:
    contact = ContactFactory.create()
    for obj in (contact, contact.company):
        assert obj is not None
        assert admin_client.get(obj.get_absolute_url()).status_code == 200


# A website typed without "https://" is completed with https (HttpsURLField).
def test_url_without_scheme_gets_https() -> None:
    form_field = Company._meta.get_field("website").formfield()
    assert form_field.clean("stepstone.de") == "https://stepstone.de"
