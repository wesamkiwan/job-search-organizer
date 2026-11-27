"""Company and contact pages."""

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from organizer.applications.selectors import applications_for_company

from .forms import CompanyForm, ContactFilterForm, ContactForm
from .models import Company, Contact
from .selectors import company_list, contact_list

# --- Companies -----------------------------------------------------------------------------


def company_list_view(request: HttpRequest) -> HttpResponse:
    """All companies, with search. The search box uses HTMX's hx-select: the server returns
    the whole page and HTMX picks the results part out of it (no extra partial template)."""
    search = request.GET.get("q", "")[:100]
    context = {"companies": company_list(search), "search": search}
    return render(request, "companies/company_list.html", context)


def company_detail(request: HttpRequest, slug: str) -> HttpResponse:
    company = get_object_or_404(Company, slug=slug)
    context = {
        "company": company,
        "applications": applications_for_company(company),
        "contacts": company.contacts.all(),
    }
    return render(request, "companies/company_detail.html", context)


def company_create(request: HttpRequest) -> HttpResponse:
    form = CompanyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        company = form.save()
        messages.success(request, f"“{company}” added.")
        return redirect(company)
    return render(request, "companies/company_form.html", {"form": form, "company": None})


def company_edit(request: HttpRequest, slug: str) -> HttpResponse:
    company = get_object_or_404(Company, slug=slug)
    form = CompanyForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Changes saved.")
        return redirect(company)
    return render(request, "companies/company_form.html", {"form": form, "company": company})


@require_POST
def company_delete(request: HttpRequest, slug: str) -> HttpResponse:
    """Delete a company. Its postings keep the company name; its contacts stay, without a
    company (both relations use on_delete=SET_NULL)."""
    company = get_object_or_404(Company, slug=slug)
    name = company.name
    company.delete()
    messages.success(request, f"“{name}” deleted. Its job postings and contacts were kept.")
    return redirect("companies:list")


# --- Contacts ------------------------------------------------------------------------------


def contact_list_view(request: HttpRequest) -> HttpResponse:
    form = ContactFilterForm(request.GET)
    context = {"contacts": contact_list(**form.values()), "form": form}
    return render(request, "companies/contact_list.html", context)


def contact_detail(request: HttpRequest, pk: int) -> HttpResponse:
    contact = get_object_or_404(Contact.objects.select_related("company"), pk=pk)
    referrals = contact.referrals.select_related("posting", "stage")
    context = {"contact": contact, "referrals": referrals}
    return render(request, "companies/contact_detail.html", context)


def contact_create(request: HttpRequest) -> HttpResponse:
    # ?company=<id> (from a company page's "Add contact" button) pre-selects the company.
    form = ContactForm(request.POST or None, initial={"company": request.GET.get("company")})
    if request.method == "POST" and form.is_valid():
        contact = form.save()
        messages.success(request, f"“{contact}” added.")
        return redirect(contact)
    return render(request, "companies/contact_form.html", {"form": form, "contact": None})


def contact_edit(request: HttpRequest, pk: int) -> HttpResponse:
    contact = get_object_or_404(Contact, pk=pk)
    form = ContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Changes saved.")
        return redirect(contact)
    return render(request, "companies/contact_form.html", {"form": form, "contact": contact})


@require_POST
def contact_delete(request: HttpRequest, pk: int) -> HttpResponse:
    contact = get_object_or_404(Contact, pk=pk)
    name = str(contact)
    contact.delete()  # applications they referred keep existing (referred_by: SET_NULL)
    messages.success(request, f"“{name}” deleted.")
    return redirect("contacts:list")
