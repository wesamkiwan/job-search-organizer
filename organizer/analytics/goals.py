"""How far along a goal is in its current week or month."""

from dataclasses import dataclass, replace
from datetime import timedelta

from .filters import FilterContext, Period
from .metrics import REGISTRY
from .models import Goal, GoalPeriod


@dataclass(frozen=True)
class GoalProgress:
    goal: Goal
    period: Period  # the current calendar week (Mon-Sun) or month, up to today
    done: int

    @property
    def remaining(self) -> int:
        return max(self.goal.target - self.done, 0)

    @property
    def ratio(self) -> float:
        """0.0 to 1.0 (capped: 12 of 10 is "reached", the bar can't overflow)."""
        return min(self.done / self.goal.target, 1.0)

    @property
    def is_reached(self) -> bool:
        return self.done >= self.goal.target


def current_period(goal: Goal, ctx: FilterContext) -> Period:
    """This calendar week (from Monday) or month, until today, whatever date range the
    dashboard shows: a weekly goal is always about THIS week."""
    today = ctx.today
    if goal.period == GoalPeriod.MONTH:
        return Period(today.replace(day=1), today)
    return Period(today - timedelta(days=today.weekday()), today)  # weekday(): Monday = 0


def goal_progress(ctx: FilterContext) -> list[GoalProgress]:
    """Progress of every active goal, with the dashboard's filters (e.g. a source)."""
    progress = []
    for goal in Goal.objects.filter(is_active=True):
        period = current_period(goal, ctx)
        result = REGISTRY[goal.metric].compute(replace(ctx, period=period))
        progress.append(GoalProgress(goal, period, int(result.value or 0)))
    return progress
