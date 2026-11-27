"""Job postings (the job ads you find) and the tags you put on them."""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone

from organizer.companies.models import Company
from organizer.core.fields import HttpsURLField
from organizer.core.models import Currency, CustomDataModel, TimeStampedModel, Tone
from organizer.sources.models import Source


class Tag(TimeStampedModel):
    """A label such as "remote", "dream job" or "Python". Used on postings (and later on
    applications)."""

    name = models.CharField(max_length=50)
    color = models.CharField(max_length=10, choices=Tone.choices, default=Tone.NEUTRAL)

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                Lower("name"),
                name="tag_name_unique_ignoring_case",
                violation_error_message="A tag with this name already exists.",
            ),
        )

    def __str__(self) -> str:
        return self.name


# --- Choices for JobPosting --------------------------------------------------------------


class RemoteType(models.TextChoices):
    ON_SITE = "on_site", "On-site"
    HYBRID = "hybrid", "Hybrid"
    REMOTE = "remote", "Remote"


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full-time"
    PART_TIME = "part_time", "Part-time"
    MINI_JOB = "mini_job", "Mini-job"
    INTERNSHIP = "internship", "Internship"
    WORKING_STUDENT = "working_student", "Working student (Werkstudent)"
    FREELANCE = "freelance", "Freelance"
    APPRENTICESHIP = "apprenticeship", "Apprenticeship (Ausbildung)"


class ContractType(models.TextChoices):
    PERMANENT = "permanent", "Permanent (unbefristet)"
    FIXED_TERM = "fixed_term", "Fixed-term (befristet)"


class Seniority(models.TextChoices):
    JUNIOR = "junior", "Junior"
    MID = "mid", "Mid-level"
    SENIOR = "senior", "Senior"
    LEAD = "lead", "Lead"
    EXECUTIVE = "executive", "Executive"


class SalaryPeriod(models.TextChoices):
    YEAR = "year", "per year"
    MONTH = "month", "per month"
    HOUR = "hour", "per hour"


class PostingLanguage(models.TextChoices):
    GERMAN = "de", "German"
    ENGLISH = "en", "English"
    OTHER = "other", "Other"


class TriageStatus(models.TextChoices):
    """What you decided about a posting you found."""

    NEW = "new", "New"  # found, not looked at yet
    SAVED = "saved", "Saved"  # interesting, maybe apply
    IGNORED = "ignored", "Ignored"  # not for me
    APPLIED = "applied", "Applied"  # an application exists


# --- JobPosting --------------------------------------------------------------------------


class JobPosting(TimeStampedModel, CustomDataModel):
    """A job ad. It exists on its own, before (or without) an application.

    Fields for automatic imports and duplicate detection (canonical_url, external_id,
    fingerprint, raw_data, description_html) come with Phases 5 and 6.
    """

    title = models.CharField(max_length=200)
    # The company may not be in your list yet (or is hidden behind an agency), so the
    # name as written in the ad is kept separately until you link it.
    company = models.ForeignKey(
        Company, on_delete=models.SET_NULL, null=True, blank=True, related_name="postings"
    )
    company_name_raw = models.CharField(
        "company name (as in the ad)",
        max_length=200,
        blank=True,
        help_text="Used when the company isn't in your list (yet).",
    )
    url = HttpsURLField("link to the ad", max_length=2000, blank=True)
    # PROTECT: a source that postings point to can't be deleted (that would lose the
    # information where those postings came from). Disable it instead.
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="postings")

    # Location
    location_text = models.CharField(
        "location", max_length=200, blank=True, help_text="As written in the ad."
    )
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    country = models.CharField(max_length=2, default="DE", help_text="Two-letter code, e.g. DE.")
    remote_type = models.CharField(max_length=10, choices=RemoteType.choices, blank=True)
    distance_km = models.PositiveIntegerField("distance (km)", null=True, blank=True)

    # The job
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices, blank=True)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, blank=True)
    seniority = models.CharField(max_length=20, choices=Seniority.choices, blank=True)
    posting_language = models.CharField(
        "language of the ad", max_length=5, choices=PostingLanguage.choices, blank=True
    )

    # Salary, stored exactly as stated in the ad (whole euros; no cents needed).
    salary_min = models.PositiveIntegerField(null=True, blank=True)
    salary_max = models.PositiveIntegerField(null=True, blank=True)
    salary_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.EUR)
    salary_period = models.CharField(
        max_length=10, choices=SalaryPeriod.choices, default=SalaryPeriod.YEAR
    )

    description_text = models.TextField("description", blank=True)

    # Dates. date_posted / valid_through come from the ad; found_at is when YOU found it.
    date_posted = models.DateField(null=True, blank=True)
    valid_through = models.DateField("apply until", null=True, blank=True)
    # default=timezone.now: the function (no parentheses!), called for each new posting.
    found_at = models.DateTimeField(default=timezone.now)

    triage_status = models.CharField(
        max_length=10, choices=TriageStatus.choices, default=TriageStatus.NEW
    )
    # ManyToMany: a posting has many tags, a tag is on many postings. Django creates a
    # hidden third table (jobs_jobposting_tags) with pairs of (posting_id, tag_id).
    tags = models.ManyToManyField(Tag, blank=True, related_name="postings")

    class Meta:
        ordering = ("-found_at",)  # "-" = descending: newest first
        indexes = (
            # The inbox will ask "all NEW postings, newest first" all the time. An index is
            # like a book's index: the database jumps to the rows instead of reading all.
            models.Index(fields=("triage_status", "-found_at"), name="posting_status_found_idx"),
        )
        constraints = (
            # The database refuses a salary range like "70,000 to 50,000".
            models.CheckConstraint(
                condition=Q(salary_min__isnull=True)
                | Q(salary_max__isnull=True)
                | Q(salary_min__lte=F("salary_max")),
                name="posting_salary_min_lte_max",
                violation_error_message="The minimum salary can't be higher than the maximum.",
            ),
        )

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        # clean() = extra validation across several fields. Forms and the admin call it
        # (through full_clean()) before saving; we attach the error to one field.
        super().clean()
        if self.valid_through and self.date_posted and self.valid_through < self.date_posted:
            raise ValidationError({"valid_through": "Can't be before the posting date."})

    @property
    def company_display(self) -> str:
        """The linked company's name, else the name from the ad.

        Uses self.company, so lists must load it with select_related("company").
        """
        if self.company_id:
            return self.company.name  # type: ignore[union-attr]
        return self.company_name_raw

    @property
    def salary_display(self) -> str:
        """The salary range as text: "55,000-70,000 EUR per year", "from 55,000 EUR ...", ""."""
        low, high = self.salary_min, self.salary_max
        if low and high:
            amount = f"{low:,}-{high:,}" if low != high else f"{low:,}"  # :, = thousands
        elif low:
            amount = f"from {low:,}"
        elif high:
            amount = f"up to {high:,}"
        else:
            return ""
        return f"{amount} {self.salary_currency} {self.get_salary_period_display()}"

    def get_absolute_url(self) -> str:
        return reverse("admin:jobs_jobposting_change", args=[self.pk])
