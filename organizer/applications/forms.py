"""Forms for the application pages."""

from django import forms

from .models import PipelineStage, Priority
from .selectors import DEFAULT_SORT, ApplicationFilters, Status


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
    sort = forms.CharField(required=False)

    def filters(self) -> ApplicationFilters:
        """The valid values as ApplicationFilters; invalid or missing ones use defaults."""
        self.is_valid()  # runs validation; cleaned_data then holds only VALID fields
        data = self.cleaned_data
        return ApplicationFilters(
            search=data.get("q") or "",
            stage=data.get("stage"),
            status=data.get("status") or Status.OPEN,
            priority=data.get("priority") or "",
            sort=data.get("sort") or DEFAULT_SORT,
        )
