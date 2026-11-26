"""Forms for the application pages."""

from typing import Any

from django import forms

from organizer.jobs.models import RemoteType

from .models import PipelineStage, Priority
from .selectors import DEFAULT_SORT, ApplicationFilters, Status, application_cities


class ApplicationFilterForm(forms.Form):
    """The filter bar above the application list.

    It reads the URL's query string (?q=...&stage=...), not a POST: filters are part of
    the address, so a filtered list can be bookmarked, shared and reloaded. A Form
    validates the values for us: an unknown stage id or status in a hand-edited URL is
    simply ignored instead of causing an error.
    """

    q = forms.CharField(label="Search", required=False, max_length=100)
    stage = forms.ModelChoiceField(
        queryset=PipelineStage.objects.all(), required=False, empty_label="All stages"
    )
    status = forms.ChoiceField(choices=Status.CHOICES, required=False)
    priority = forms.ChoiceField(choices=(("", "Any priority"), *Priority.choices), required=False)
    city = forms.ChoiceField(label="Location", required=False)  # choices: see __init__
    remote_type = forms.ChoiceField(
        label="Work mode", choices=(("", "Any work mode"), *RemoteType.choices), required=False
    )
    sort = forms.CharField(required=False)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # The cities come from the database, so they are read each time the form is made
        # (a class-level choices list would be frozen at server start).
        cities = [(city, city) for city in application_cities()]
        self.fields["city"].choices = [("", "Any location"), *cities]  # type: ignore[attr-defined]

    def filters(self) -> ApplicationFilters:
        """The valid values as ApplicationFilters; invalid or missing ones use defaults."""
        self.is_valid()  # runs validation; cleaned_data then holds only VALID fields
        data = self.cleaned_data
        return ApplicationFilters(
            search=data.get("q") or "",
            stage=data.get("stage"),
            status=data.get("status") or Status.OPEN,
            priority=data.get("priority") or "",
            city=data.get("city") or "",
            remote_type=data.get("remote_type") or "",
            sort=data.get("sort") or DEFAULT_SORT,
        )
