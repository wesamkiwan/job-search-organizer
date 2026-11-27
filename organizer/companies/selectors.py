"""Read queries for companies and contacts."""

from django.db.models import Count, Q, QuerySet

from .models import Company, Contact, ContactKind


def company_list(search: str = "") -> QuerySet[Company]:
    """Companies A to Z with their numbers of applications and contacts.

    Careful with two Counts over two different relations: the database JOINs both, so a
    company with 3 applications and 2 contacts produces 3 x 2 = 6 rows, and both counts
    would say 6. distinct=True counts each application / contact only once.
    """
    companies = Company.objects.annotate(
        application_count=Count("postings__application", distinct=True),
        open_application_count=Count(
            "postings__application",
            filter=Q(postings__application__closed_at__isnull=True),
            distinct=True,
        ),
        contact_count=Count("contacts", distinct=True),
    )
    if search := search.strip():  # := assigns and tests in one step ("walrus operator")
        companies = companies.filter(
            Q(name__icontains=search)
            | Q(industry__icontains=search)
            | Q(headquarters__icontains=search)
            | Q(locations__icontains=search)
        )
    return companies.order_by("name")


def contact_list(search: str = "", kind: str = "") -> QuerySet[Contact]:
    contacts = Contact.objects.select_related("company")
    if search := search.strip():
        contacts = contacts.filter(
            Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(email__icontains=search)
            | Q(job_title__icontains=search)
            | Q(company__name__icontains=search)
        )
    if kind in ContactKind.values:
        contacts = contacts.filter(kind=kind)
    return contacts.order_by("last_name", "first_name")
