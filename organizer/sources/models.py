"""Where job postings come from: StepStone, LinkedIn, a company website, ...

Phase 1 keeps this small (name, kind, website). Phase 6 adds the automatic part
(adapter, config, field mapping, search profiles, runs); see docs/04-job-sources.md.
"""

from django.db import models
from django.db.models.functions import Lower

from organizer.core.fields import HttpsURLField
from organizer.core.models import TimeStampedModel


class SourceKind(models.TextChoices):
    """HOW postings arrive from this source (not which website it is)."""

    MANUAL = "manual", "Entered by hand"
    URL_IMPORT = "url_import", "URL import"
    BOOKMARKLET = "bookmarklet", "Bookmarklet"
    EMAIL_ALERT = "email_alert", "Email alert"
    API = "api", "API"
    RSS = "rss", "RSS feed"
    JSONLD = "jsonld", "Structured data (JSON-LD)"
    HTML = "html", "Web page (HTML)"


class Source(TimeStampedModel):
    """A place where you find jobs. Postings point to it, so the dashboard can later
    answer "which source brings me the most interviews?"."""

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=20, choices=SourceKind.choices, default=SourceKind.MANUAL)
    website = HttpsURLField(blank=True)
    is_enabled = models.BooleanField(
        "enabled", default=True, help_text="Disabled sources are hidden when you add a posting."
    )

    class Meta:
        ordering = ("name",)
        constraints = (
            models.UniqueConstraint(
                Lower("name"),
                name="source_name_unique_ignoring_case",
                violation_error_message="A source with this name already exists.",
            ),
        )

    def __str__(self) -> str:
        return self.name
