"""The dashboard's filter bar, and the goal form."""

from datetime import date
from typing import Any, ClassVar

from django import forms

from organizer.applications.models import Channel
from organizer.core.forms import DateInput
from organizer.jobs.models import EmploymentType, RemoteType, Tag
from organizer.sources.models import Source

from .filters import FilterContext, Period, Preset, period_for
from .models import Goal

# Filters that are part of the dashboard URL, in the order they appear in links.
FILTER_FIELDS = (
    "range",
    "start",
    "end",
    "source",
    "channel",
    "tag",
    "remote_type",
    "employment_type",
)


class DashboardFilterForm(forms.Form):
    """Reads the dashboard's query string (?range=30d&source=2...), like the application
    list's filter form: filters are part of the URL, so a view can be bookmarked and
    shared, and invalid values in a hand-edited URL are simply ignored."""

    range = forms.ChoiceField(
        label="Period", choices=Preset.choices, required=False, initial=Preset.LAST_30_DAYS
    )
    start = forms.DateField(label="From", required=False, widget=DateInput())
    end = forms.DateField(label="To", required=False, widget=DateInput())
    source = forms.ModelChoiceField(
        queryset=Source.objects.order_by("name"), required=False, empty_label="All sources"
    )
    channel = forms.ChoiceField(choices=(("", "All channels"), *Channel.choices), required=False)
    tag = forms.ModelChoiceField(queryset=Tag.objects.all(), required=False, empty_label="All tags")
    remote_type = forms.ChoiceField(
        label="Work mode", choices=(("", "Any work mode"), *RemoteType.choices), required=False
    )
    employment_type = forms.ChoiceField(
        label="Employment",
        choices=(("", "Any employment"), *EmploymentType.choices),
        required=False,
    )

    def _data(self) -> dict[str, Any]:
        self.is_valid()  # cleaned_data then holds only the VALID fields
        return getattr(self, "cleaned_data", {})

    def context(self, today: date | None = None) -> FilterContext:
        data = self._data()
        period = period_for(
            data.get("range") or Preset.LAST_30_DAYS,
            today=today,
            start=data.get("start"),
            end=data.get("end"),
        )
        kwargs: dict[str, Any] = {"period": period}
        if today is not None:
            kwargs["today"] = today
        return FilterContext(
            **kwargs,
            sources=(data["source"].pk,) if data.get("source") else (),
            channels=(data["channel"],) if data.get("channel") else (),
            tags=(data["tag"].pk,) if data.get("tag") else (),
            remote_types=(data["remote_type"],) if data.get("remote_type") else (),
            employment_types=(data["employment_type"],) if data.get("employment_type") else (),
        )

    def query(self) -> dict[str, str]:
        """The valid, non-empty filter values as text: for links that keep the filters."""
        data = self._data()
        query = {}
        for name in FILTER_FIELDS:
            value = data.get(name)
            if value in (None, ""):
                continue
            if isinstance(value, date):
                value = value.isoformat()
            elif hasattr(value, "pk"):
                value = value.pk
            query[name] = str(value)
        return query

    @property
    def has_filters(self) -> bool:
        """Any filter besides the period?"""
        return any(name in self.query() for name in FILTER_FIELDS[3:])


def describe(period: Period) -> str:
    """'12 Nov 2026 to 28 Nov 2026' (with an en dash), or 'Until 28 Nov 2026' for all time."""
    end = f"{period.end:%d %b %Y}"
    return (
        f"Until {end}" if period.start is None else f"{period.start:%d %b %Y} \u2013 {end}"
    )  # en dash


class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = ("target", "period")
        labels: ClassVar[dict[str, str]] = {"target": "Applications"}
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "target": forms.NumberInput(attrs={"min": 1, "max": 999})
        }
