"""Applications, the pipeline stages they move through, their timeline and tasks.

Important rule: an application's stage is ONLY changed through the functions in
services.py (create_application, change_stage, close_application). They keep the
timeline, the dates and the posting's status consistent. Never set .stage and save().
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils import timezone

from organizer.companies.models import Contact
from organizer.core.models import Currency, CustomDataModel, TimeStampedModel, Tone
from organizer.jobs.models import JobPosting, Tag

# --- PipelineStage -----------------------------------------------------------------------


class StageCategory(models.TextChoices):
    """What a stage MEANS. The app's logic only looks at the category, never at the
    stage's name, so you can rename "Interviewing" to "Interviews" without breaking it."""

    SAVED = "saved", "Saved (not applied yet)"
    APPLIED = "applied", "Applied"
    IN_PROGRESS = "in_progress", "In progress"
    OFFER = "offer", "Offer"
    WON = "won", "Accepted"
    LOST = "lost", "Lost (rejected, ghosted)"
    WITHDRAWN = "withdrawn", "Withdrawn"


# Categories that end an application: entering one of them closes it.
FINAL_CATEGORIES = frozenset({StageCategory.WON, StageCategory.LOST, StageCategory.WITHDRAWN})


class PipelineStage(TimeStampedModel):
    """A column of the kanban board: Saved, Applied, Screening, Interviewing, ..."""

    name = models.CharField(max_length=50)
    # Gaps of 10 between the defaults (10, 20, 30...) leave room to insert a stage later.
    order = models.PositiveSmallIntegerField(default=0, help_text="Smaller numbers come first.")
    color = models.CharField(max_length=10, choices=Tone.choices, default=Tone.NEUTRAL)
    category = models.CharField(max_length=20, choices=StageCategory.choices)
    is_default_for_category = models.BooleanField(
        "default for its category",
        default=False,
        help_text="Used when the app needs “a stage of this category”, e.g. Rejected for "
        "closing an application as lost.",
    )
    # Roles for the dashboard. Categories are broad ("Screening" and "Interviewing" are
    # both in progress; "Rejected" and "Ghosted" are both lost), and the app never looks
    # at a stage's NAME, so these switches say what a stage means for the statistics.
    counts_as_interview = models.BooleanField(
        default=False,
        help_text="Reaching this stage counts as getting an interview (interview rate).",
    )
    counts_as_ghosted = models.BooleanField(
        default=False,
        help_text="Ending in this stage means the employer never answered (ghosting rate).",
    )

    class Meta:
        ordering = ("order", "pk")
        constraints = (
            models.UniqueConstraint(
                Lower("name"),
                name="stage_name_unique_ignoring_case",
                violation_error_message="A stage with this name already exists.",
            ),
            # A *partial* unique constraint: only rows WHERE is_default_for_category is
            # true take part, so each category has at most ONE default stage.
            models.UniqueConstraint(
                fields=("category",),
                condition=Q(is_default_for_category=True),
                name="one_default_stage_per_category",
                violation_error_message="This category already has a default stage.",
            ),
        )

    def __str__(self) -> str:
        return self.name

    @property
    def is_final(self) -> bool:
        return self.category in FINAL_CATEGORIES


# --- Application -------------------------------------------------------------------------


class Channel(models.TextChoices):
    """HOW you applied."""

    COMPANY_PORTAL = "company_portal", "Company careers portal"
    EMAIL = "email", "Email"
    APPLICANT_SYSTEM = "applicant_system", "Applicant tracking system (e.g. Workday)"
    LINKEDIN_EASY_APPLY = "linkedin_easy_apply", "LinkedIn Easy Apply"
    XING = "xing", "Xing"
    RECRUITER = "recruiter", "Through a recruiter"
    REFERRAL = "referral", "Referral"
    OTHER = "other", "Other"


class Priority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class RejectionReason(models.TextChoices):
    NO_REASON_GIVEN = "no_reason_given", "No reason given"
    OTHER_CANDIDATE = "other_candidate", "Chose another candidate"
    SKILLS_MISMATCH = "skills_mismatch", "Skills don't match"
    EXPERIENCE_LEVEL = "experience_level", "Too junior / too senior"
    SALARY = "salary", "Salary expectations"
    LANGUAGE = "language", "Language requirements"
    POSITION_FILLED = "position_filled", "Position filled or cancelled"
    OTHER = "other", "Other"


class Application(TimeStampedModel, CustomDataModel):
    """Your application for one job posting."""

    # OneToOne = a ForeignKey with unique=True: one posting has AT MOST one application.
    # PROTECT: a posting with an application can't be deleted by accident (you'd lose
    # the whole history); delete the application first if you really mean it.
    posting = models.OneToOneField(JobPosting, on_delete=models.PROTECT, related_name="application")
    # The current stage. Set ONLY through services.py (see the module docstring).
    stage = models.ForeignKey(PipelineStage, on_delete=models.PROTECT, related_name="applications")

    applied_on = models.DateField(null=True, blank=True, help_text="Empty while only saved.")
    channel = models.CharField(max_length=30, choices=Channel.choices, blank=True)
    referred_by = models.ForeignKey(
        Contact,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="referrals",
        help_text="The person who referred you, if any.",
    )

    salary_expectation = models.PositiveIntegerField(
        null=True, blank=True, help_text="Gehaltsvorstellung, as stated in your application."
    )
    salary_expectation_currency = models.CharField(
        "currency", max_length=3, choices=Currency.choices, default=Currency.EUR
    )
    earliest_start_date = models.DateField(null=True, blank=True)
    notice_period = models.CharField(
        max_length=100, blank=True, help_text="Kündigungsfrist, e.g. “3 months to month end”."
    )

    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    interest = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="How much you want this job, 1 to 5.",
    )
    follow_up_on = models.DateField("follow up on", null=True, blank=True)

    # Filled by the services when the application reaches a final stage.
    closed_at = models.DateTimeField(null=True, blank=True)
    # For lost applications: the stage reached BEFORE the rejection (e.g. "Interviewing").
    # related_name="+" means: no reverse relation (stage.<something> isn't needed).
    outcome_stage = models.ForeignKey(
        PipelineStage, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    rejection_reason = models.CharField(max_length=30, choices=RejectionReason.choices, blank=True)
    rejection_details = models.TextField(blank=True)

    notes = models.TextField(blank=True)
    is_archived = models.BooleanField("archived", default=False)
    tags = models.ManyToManyField(Tag, blank=True, related_name="applications")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        # Uses the posting: lists of applications should select_related("posting").
        return self.posting.title

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    @property
    def salary_expectation_display(self) -> str:
        if not self.salary_expectation:
            return ""
        return f"{self.salary_expectation:,} {self.salary_expectation_currency}"

    def get_absolute_url(self) -> str:
        return reverse("applications:detail", args=[self.pk])


# --- ApplicationEvent (the timeline) -----------------------------------------------------


class EventKind(models.TextChoices):
    STAGE_CHANGE = "stage_change", "Stage change"
    NOTE = "note", "Note"
    EMAIL_SENT = "email_sent", "Email sent"
    EMAIL_RECEIVED = "email_received", "Email received"
    CALL = "call", "Call"
    FOLLOW_UP = "follow_up", "Follow-up"
    DOCUMENT_SENT = "document_sent", "Document sent"
    OTHER = "other", "Other"


class ApplicationEvent(TimeStampedModel):
    """One entry on an application's timeline."""

    # CASCADE: the timeline belongs to the application; deleting it deletes its events.
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=EventKind.choices)
    # PROTECT: a stage that appears in someone's history can't be deleted.
    from_stage = models.ForeignKey(
        PipelineStage, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    to_stage = models.ForeignKey(
        PipelineStage, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    # When it HAPPENED (can be in the past: "they called last Tuesday"), as opposed to
    # created_at, which is when you wrote it down.
    occurred_at = models.DateTimeField(default=timezone.now)
    summary = models.CharField(max_length=200, blank=True)
    details = models.TextField(blank=True)

    class Meta:
        ordering = ("-occurred_at", "-pk")  # newest first; pk breaks ties
        constraints = (
            # A stage change must say which stage it went to.
            models.CheckConstraint(
                condition=~Q(kind="stage_change") | Q(to_stage__isnull=False),
                name="stage_change_event_has_to_stage",
            ),
        )

    def __str__(self) -> str:
        return self.summary or self.get_kind_display()


# --- Task --------------------------------------------------------------------------------


class Task(TimeStampedModel):
    """A to-do, e.g. "Send thank-you email". Optionally linked to an application."""

    title = models.CharField(max_length=200)
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, null=True, blank=True, related_name="tasks"
    )
    due_on = models.DateField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        # Open tasks first (done_at empty), then by due date (no date last), then oldest.
        ordering = (
            F("done_at").asc(nulls_first=True),
            F("due_on").asc(nulls_last=True),
            "pk",
        )

    def __str__(self) -> str:
        return self.title

    @property
    def is_done(self) -> bool:
        return self.done_at is not None
