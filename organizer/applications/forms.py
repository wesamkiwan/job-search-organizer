"""Forms for the application pages."""

from typing import Any, ClassVar

from django import forms

from organizer.companies.models import Company
from organizer.companies.services import find_or_create_company
from organizer.core.forms import DateInput, DateTimeInput, now_for_input
from organizer.core.models import UserSettings
from organizer.jobs.models import JobPosting, RemoteType
from organizer.sources.models import Source

from .models import (
    FINAL_CATEGORIES,
    Application,
    ApplicationEvent,
    EventKind,
    PipelineStage,
    Priority,
    RejectionReason,
    StageCategory,
)
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


# --- Create / edit -----------------------------------------------------------------------


class PostingForm(forms.ModelForm):
    """The job part of the "Add application" and "Edit" pages.

    company_name is not a model field: you type a name, and save() links the existing
    company with that name or creates it (find_or_create_company).
    """

    company_name = forms.CharField(
        label="Company",
        max_length=200,
        required=False,
        help_text="An existing company is linked; a new name adds the company.",
        widget=forms.TextInput(attrs={"list": "company-names"}),
    )
    # Fields that span the whole width of the form (used by the template).
    wide_fields = ("title", "url", "description_text")

    class Meta:
        model = JobPosting
        fields = (
            "title",
            "company_name",
            "source",
            "url",
            "city",
            "remote_type",
            "employment_type",
            "contract_type",
            "seniority",
            "salary_min",
            "salary_max",
            "salary_currency",
            "salary_period",
            "description_text",
        )
        labels: ClassVar[dict[str, str]] = {
            "title": "Job title",
            "salary_min": "Salary from",
            "salary_max": "Salary to",
        }
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "description_text": forms.Textarea(attrs={"rows": 6}),
            "url": forms.URLInput(attrs={"placeholder": "https://"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        posting: JobPosting = self.instance
        # Only enabled sources are offered (plus the posting's own, even if disabled now).
        sources = Source.objects.filter(is_enabled=True)
        if posting.source_id:
            sources = sources | Source.objects.filter(pk=posting.source_id)
        self.fields["source"].queryset = sources  # type: ignore[attr-defined]
        if posting.pk:
            self.fields["company_name"].initial = posting.company_display
        else:
            self.fields["source"].initial = Source.objects.filter(name="Manual").first()
            self.fields["salary_currency"].initial = UserSettings.load().default_currency

    def save(self, commit: bool = True) -> JobPosting:
        posting: JobPosting = super().save(commit=False)
        posting.company = find_or_create_company(self.cleaned_data["company_name"])
        posting.company_name_raw = posting.company.name if posting.company else ""
        if commit:
            posting.save()
            self.save_m2m()
        return posting


class ApplicationForm(forms.ModelForm):
    """The application part of the "Add application" and "Edit" pages.

    The stage can be chosen only when ADDING. Afterwards it changes through the stage
    form on the detail page (services.change_stage), never by editing.
    """

    wide_fields = ("tags", "notes")

    class Meta:
        model = Application
        fields = (
            "stage",
            "applied_on",
            "channel",
            "priority",
            "interest",
            "follow_up_on",
            "referred_by",
            "salary_expectation",
            "salary_expectation_currency",
            "earliest_start_date",
            "notice_period",
            "tags",
            "notes",
        )
        labels: ClassVar[dict[str, str]] = {"stage": "Starting stage", "interest": "Interest (1-5)"}
        help_texts: ClassVar[dict[str, str]] = {
            "applied_on": "Leave empty for today (not needed while only saved)."
        }
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "applied_on": DateInput(),
            "follow_up_on": DateInput(),
            "earliest_start_date": DateInput(),
            "tags": forms.CheckboxSelectMultiple(),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["stage"]
        else:
            self.fields["stage"].initial = PipelineStage.objects.filter(
                category=StageCategory.APPLIED, is_default_for_category=True
            ).first()
            self.fields[
                "salary_expectation_currency"
            ].initial = UserSettings.load().default_currency


def company_names() -> list[str]:
    """All company names, for the type-ahead suggestions (<datalist>) of company_name."""
    return list(Company.objects.order_by("name").values_list("name", flat=True))


# --- Actions on the detail page ------------------------------------------------------------


class StageChangeForm(forms.Form):
    stage = forms.ModelChoiceField(queryset=PipelineStage.objects.none(), label="New stage")
    occurred_at = forms.DateTimeField(label="When", widget=DateTimeInput(), initial=now_for_input)
    note = forms.CharField(label="Note", required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args: Any, application: Application, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Every stage except the current one.
        stages = PipelineStage.objects.exclude(pk=application.stage_id)
        self.fields["stage"].queryset = stages  # type: ignore[attr-defined]


class CloseForm(forms.Form):
    stage = forms.ModelChoiceField(
        queryset=PipelineStage.objects.filter(category__in=FINAL_CATEGORIES),
        label="Outcome",
        help_text="Rejected, ghosted, withdrawn or accepted.",
    )
    reason = forms.ChoiceField(
        label="Rejection reason",
        choices=(("", "—"), *RejectionReason.choices),
        required=False,
        help_text="Only for rejections.",
    )
    details = forms.CharField(
        label="Details", required=False, widget=forms.Textarea(attrs={"rows": 2})
    )
    occurred_at = forms.DateTimeField(label="When", widget=DateTimeInput(), initial=now_for_input)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["stage"].initial = PipelineStage.objects.filter(
            category=StageCategory.LOST, is_default_for_category=True
        ).first()


class EventForm(forms.ModelForm):
    """Add a note, call, email, ... to the timeline."""

    class Meta:
        model = ApplicationEvent
        fields = ("kind", "summary", "occurred_at", "details")
        labels: ClassVar[dict[str, str]] = {"kind": "Type", "occurred_at": "When"}
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "occurred_at": DateTimeInput(),
            "details": forms.Textarea(attrs={"rows": 3}),
            "summary": forms.TextInput(attrs={"placeholder": "e.g. Call with the recruiter"}),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Stage changes are made with the stage form, so they are not offered here.
        kinds = [(value, label) for value, label in EventKind.choices if value != "stage_change"]
        self.fields["kind"].choices = kinds  # type: ignore[attr-defined]
        self.fields["kind"].initial = EventKind.NOTE
        self.fields["summary"].required = True
        self.fields["occurred_at"].initial = now_for_input
