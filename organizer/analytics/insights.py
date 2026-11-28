"""The insights panel: plain sentences computed from the data by simple rules.

Every rule needs enough data first (performance.MIN_SAMPLE applications per group):
with 2 applications, "50% vs 0%" is chance, not a finding. When no rule has enough data,
the panel says so instead of guessing. Later, the AI module can add richer insights.
"""

from dataclasses import dataclass, replace
from typing import Any

from organizer.core.models import UserSettings

from . import metrics
from .filters import FilterContext, Period
from .goals import goal_progress
from .performance import MIN_SAMPLE, Row, channels, document_rows, sources
from .widgets import Links, Table, percent, widget

# A difference only counts as a finding when it is big in both ways: at least 1.5 times
# as high, AND at least 10 percentage points apart (5% vs 8% is 1.6x but hardly matters).
MIN_RATIO = 1.5
MIN_POINTS = 0.10


@dataclass(frozen=True)
class Insight:
    text: str
    tone: str = "info"  # "info", "success" or "warning": the badge colour (+ its label)
    url: str = ""
    link_text: str = ""


def compare_rows(rows: list[Row], rate: str, what: str, noun: str) -> Insight | None:
    """The best vs. the worst group, if both have enough data and differ clearly."""
    usable = [r for r in rows if not r.few and getattr(r, rate) is not None]
    if len(usable) < 2:
        return None
    best = max(usable, key=lambda r: getattr(r, rate))
    worst = min(usable, key=lambda r: getattr(r, rate))
    high, low = getattr(best, rate), getattr(worst, rate)
    if high - low < MIN_POINTS or (low and high / low < MIN_RATIO):
        return None
    # \u00d7 is the multiplication sign ("3.0\u00d7 higher"); with 0% as the low value there is
    # no ratio to print.
    times = f"{high / low:.1f}\u00d7 higher" if low else "a clearly higher"
    return Insight(
        f"{noun} “{best.label}” has {times} {what} than “{worst.label}” "
        f"({percent(high)} vs {percent(low)}, from {best.sent} and {worst.sent} applications).",
        "success",
    )


def silent_applications(ctx: FilterContext, links: Links) -> Insight | None:
    days = UserSettings.load().ghosted_after_days
    all_time = replace(ctx, period=Period(None, ctx.today))
    silent = metrics.ghosted(all_time).filter(closed_at__isnull=True).count()
    if not silent:
        return None
    return Insight(
        f"{silent} application{'s have' if silent != 1 else ' has'} had no response for "
        f"{days}+ days. Follow up, or close {'them' if silent != 1 else 'it'} as ghosted?",
        "warning",
        links.group("ghosted", range="all"),
        "Show them",
    )


def behind_goal(ctx: FilterContext) -> Insight | None:
    for progress in goal_progress(ctx):
        if progress.goal.period == "week" and not progress.is_reached:
            days_left = 6 - ctx.today.weekday()
            when = "today is the last day" if not days_left else f"{days_left} days left"
            return Insight(
                f"You are {progress.remaining} application{'s' if progress.remaining != 1 else ''} "
                f"behind this week's goal ({progress.done} of {progress.goal.target}, {when}).",
                "warning",
            )
    return None


def best_document_version(ctx: FilterContext) -> Insight | None:
    rows = document_rows(ctx)
    return compare_rows(rows, "response_rate", "response rate", "Document")


def _rows(data: dict[str, Any]) -> list[Row]:
    return data["sections"][0]["rows"] if data["sections"] else []


def build_insights(ctx: FilterContext, links: Links) -> list[Insight]:
    """Every rule once; the ones without a finding (or without enough data) drop out."""
    found = [
        compare_rows(_rows(channels(ctx, links)), "interview_rate", "interview rate", "Channel"),
        compare_rows(_rows(sources(ctx, links)), "response_rate", "response rate", "Source"),
        best_document_version(ctx),
        silent_applications(ctx, links),
        behind_goal(ctx),
    ]
    return [insight for insight in found if insight is not None]


@widget(
    "insights",
    "Insights",
    f"Findings from your data. Each needs at least {MIN_SAMPLE} applications per group.",
    "insights.html",
    size="full",
)
def insights(ctx: FilterContext, links: Links) -> dict[str, Any]:
    found = build_insights(ctx, links)
    return {
        "insights": found,
        "min_sample": MIN_SAMPLE,
        "table": Table(("Insight",), [(insight.text,) for insight in found]),
    }
