"""Write operations for companies."""

from .models import Company


def find_or_create_company(name: str) -> Company | None:
    """The company with this name (ignoring upper/lower case), created if it's new.

    Lets forms take a plain company name: typing "acme" links the existing "ACME" instead
    of creating a duplicate. Returns None for an empty name (company unknown).
    """
    name = " ".join(name.split())  # trim and collapse spaces: "  ACME   GmbH " → "ACME GmbH"
    if not name:
        return None
    company = Company.objects.filter(name__iexact=name).first()
    if company is None:
        company = Company.objects.create(name=name)
    return company
