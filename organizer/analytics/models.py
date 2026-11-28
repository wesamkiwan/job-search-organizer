"""Configuration for the dashboard: goals (and later the layout, batch D)."""

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from organizer.core.models import TimeStampedModel


class GoalMetric(models.TextChoices):
    """What a goal counts. Only metrics where "more per week" is the aim make sense here."""

    APPLICATIONS_SENT = "applications_sent", "Applications sent"


class GoalPeriod(models.TextChoices):
    WEEK = "week", "per week"
    MONTH = "month", "per month"


class Goal(TimeStampedModel):
    """A target such as "10 applications per week"."""

    metric = models.CharField(
        max_length=50, choices=GoalMetric.choices, default=GoalMetric.APPLICATIONS_SENT
    )
    target = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    period = models.CharField(max_length=10, choices=GoalPeriod.choices, default=GoalPeriod.WEEK)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        ordering = ("metric", "period")
        constraints = (
            # Two ACTIVE goals for the same thing would contradict each other. (Inactive
            # ones can pile up as history.) A partial unique constraint, as for stages.
            models.UniqueConstraint(
                fields=("metric", "period"),
                condition=Q(is_active=True),
                name="one_active_goal_per_metric_and_period",
                violation_error_message="There is already an active goal for this.",
            ),
            models.CheckConstraint(condition=Q(target__gte=1), name="goal_target_at_least_1"),
        )

    def __str__(self) -> str:
        return f"{self.target} {self.get_metric_display().lower()} {self.get_period_display()}"
