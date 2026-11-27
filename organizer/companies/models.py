"""Companies you apply to, and the people (contacts) you deal with there."""

from typing import Any

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.text import slugify

from organizer.core.fields import HttpsURLField
from organizer.core.models import CustomDataModel, TimeStampedModel

# Slugs that are page names under /companies/ (e.g. /companies/new/ adds a company), so no
# company may get them: a company called "New" gets the slug "new-2".
RESERVED_SLUGS = frozenset({"new"})


class CompanySize(models.TextChoices):
    # Format: CONSTANT = "value stored in the database", "label shown to the user"
    S1_10 = "1-10", "1-10 employees"
    S11_50 = "11-50", "11-50 employees"
    S51_200 = "51-200", "51-200 employees"
    S201_1000 = "201-1000", "201-1,000 employees"
    S1001_5000 = "1001-5000", "1,001-5,000 employees"
    S5000_PLUS = "5000+", "5,000+ employees"


class Company(TimeStampedModel, CustomDataModel):
    """An employer or a recruiting agency."""

    name = models.CharField(max_length=200)
    # A slug is a URL-friendly version of the name: "Müller & Söhne GmbH" -> "muller-sohne-gmbh".
    # It's filled automatically in save() and never changes afterwards, so links stay valid.
    slug = models.SlugField(max_length=220, unique=True, blank=True)

    website = HttpsURLField(blank=True)
    careers_url = HttpsURLField("careers page", blank=True)
    linkedin_url = HttpsURLField("LinkedIn page", blank=True)

    industry = models.CharField(max_length=100, blank=True)
    size = models.CharField(max_length=10, choices=CompanySize.choices, blank=True)
    headquarters = models.CharField(max_length=200, blank=True)
    locations = models.CharField(
        max_length=300, blank=True, help_text="Other offices, e.g. “Berlin, Munich, remote”."
    )

    description = models.TextField(blank=True, help_text="What the company does.")
    notes = models.TextField(blank=True, help_text="Your own notes.")
    # null=True: "not rated yet" is stored as NULL (no value), which is different from 0.
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Your personal impression, 1 (poor) to 5 (great).",
    )
    is_recruiting_agency = models.BooleanField(
        "recruiting agency",
        default=False,
        help_text="A headhunter or agency that recruits for other companies.",
    )

    class Meta:
        verbose_name_plural = "companies"
        ordering = ("name",)
        constraints = (
            # No two companies with the same name, ignoring upper/lower case
            # ("SAP" and "sap" are the same company). Enforced by the database itself.
            models.UniqueConstraint(
                Lower("name"),
                name="company_name_unique_ignoring_case",
                violation_error_message="A company with this name already exists.",
            ),
        )

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self) -> str:
        """slugify(name), plus -2, -3, ... if that slug is already taken."""
        # Different names can give the same slug ("A&B" and "A B" both -> "ab"/"a-b").
        base = slugify(self.name)[:200] or "company"  # name of only symbols -> ""
        slug, number = base, 2
        while slug in RESERVED_SLUGS or (
            Company.objects.filter(slug=slug).exclude(pk=self.pk).exists()
        ):
            slug = f"{base}-{number}"
            number += 1
        return slug

    def get_absolute_url(self) -> str:
        # Django's convention: "where does this object live?" (redirect(obj), the admin's
        # "View on site" button). Company pages use the readable slug in the URL.
        return reverse("companies:detail", args=[self.slug])


class ContactKind(models.TextChoices):
    INTERNAL_RECRUITER = "internal_recruiter", "Internal recruiter"
    EXTERNAL_RECRUITER = "external_recruiter", "External recruiter (headhunter)"
    HIRING_MANAGER = "hiring_manager", "Hiring manager"
    EMPLOYEE = "employee", "Employee"
    REFERRAL = "referral", "Referral"
    OTHER = "other", "Other"


class Contact(TimeStampedModel, CustomDataModel):
    """A person: recruiter, hiring manager, someone who referred you, ..."""

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)  # sometimes you only know "Anna"
    job_title = models.CharField(max_length=150, blank=True)

    # ForeignKey = "many contacts belong to one company". The database stores the
    # company's id in a column called company_id.
    company = models.ForeignKey(
        Company,
        # What happens to the contact when its company is deleted? SET_NULL: the person
        # stays in your contacts, just without a company (CASCADE would delete them too).
        on_delete=models.SET_NULL,
        null=True,  # the database column may be empty...
        blank=True,  # ...and forms allow leaving it empty (freelance recruiter, unknown).
        # The name for the reverse direction: company.contacts.all()
        related_name="contacts",
    )
    kind = models.CharField(max_length=20, choices=ContactKind.choices, default=ContactKind.OTHER)

    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    linkedin_url = HttpsURLField("LinkedIn profile", blank=True)

    notes = models.TextField(blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("last_name", "first_name")

    def __str__(self) -> str:
        # Only own fields: mentioning self.company here would run one extra database
        # query per contact wherever a list of contacts is shown (the "N+1" problem).
        return self.full_name

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_absolute_url(self) -> str:
        return reverse("contacts:detail", args=[self.pk])
