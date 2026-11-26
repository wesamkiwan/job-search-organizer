"""Models shared by the whole app."""

from typing import Any

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TimeStampedModel(models.Model):
    """Base class that adds "when was this created / last changed" to a model.

    abstract = True: Django creates NO table for this class. Every model that inherits
    from it gets the two columns in its own table instead. Write them once, use everywhere.
    """

    # auto_now_add: set once, when the row is first saved (INSERT). Never changes after.
    created_at = models.DateTimeField(auto_now_add=True)
    # auto_now: set again on every save() (INSERT and UPDATE).
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CustomDataModel(models.Model):
    """Base class for models whose user-defined fields live in a JSON column.

    In Phase 3 the user defines extra fields (FieldDefinition); their values are stored
    here as {"field_key": value, ...}. See docs/adr/0002-custom-fields-json.md.
    """

    # default=dict (the function, NOT {}): every row gets its own new empty dict.
    # A literal {} would be one shared object, a classic Python bug.
    custom_data = models.JSONField("custom fields", default=dict, blank=True)

    class Meta:
        abstract = True


class Currency(models.TextChoices):
    EUR = "EUR", "Euro (EUR)"
    CHF = "CHF", "Swiss franc (CHF)"
    GBP = "GBP", "Pound sterling (GBP)"
    USD = "USD", "US dollar (USD)"


class DateFormat(models.TextChoices):
    # The stored value is a Django date format string, so templates can use it
    # directly: {{ some_date|date:user_settings.date_format }}
    GERMAN = "d.m.Y", "25.11.2026 (German)"
    ISO = "Y-m-d", "2026-11-25 (ISO)"
    BRITISH = "d/m/Y", "25/11/2026 (British)"


class UserSettings(TimeStampedModel):
    """App-wide preferences. There is only ever one row (a "singleton").

    The app has a single user (ADR 0004), so the settings belong to the app, not to a
    user: no foreign key. Always read them with UserSettings.load().
    """

    SINGLETON_PK = 1

    home_location = models.CharField(
        max_length=200,
        blank=True,
        help_text="City or postal code, used later to show the distance to a job.",
    )
    default_currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.EUR,
        help_text="Pre-selected when you enter a salary.",
    )
    ghosted_after_days = models.PositiveSmallIntegerField(
        "ghosted after (days)",
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
        help_text="Days without a response before an application counts as ghosted.",
    )
    date_format = models.CharField(
        max_length=10,
        choices=DateFormat.choices,
        default=DateFormat.GERMAN,
    )

    class Meta:
        verbose_name = "settings"
        verbose_name_plural = "settings"

    def __str__(self) -> str:
        return "Settings"

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Whatever happens, there is only row 1: saving a "new" object updates it.
        self.pk = self.SINGLETON_PK
        if self._state.adding:
            # A brand-new Python object (not loaded from the database). If row 1 already
            # exists, Django will UPDATE it, and auto_now_add only fills created_at on an
            # INSERT, so we would write NULL into it. Keep the row's real creation time.
            # (If row 1 does not exist yet, this finds nothing and the INSERT fills it.)
            existing = (
                UserSettings.objects.filter(pk=self.SINGLETON_PK)
                .values_list("created_at", flat=True)
                .first()
            )
            if existing is not None:
                self.created_at = existing
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "UserSettings":
        """Return the settings, creating them with the defaults on first use."""
        obj, _created = cls.objects.get_or_create(pk=cls.SINGLETON_PK)
        return obj
