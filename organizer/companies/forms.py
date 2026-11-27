"""Forms for the company and contact pages."""

from typing import Any, ClassVar

from django import forms

from organizer.core.forms import DateTimeInput

from .models import Company, Contact, ContactKind


class CompanyForm(forms.ModelForm):
    wide_fields = ("name", "description", "notes")

    class Meta:
        model = Company
        fields = (
            "name",
            "industry",
            "size",
            "headquarters",
            "locations",
            "website",
            "careers_url",
            "linkedin_url",
            "rating",
            "is_recruiting_agency",
            "description",
            "notes",
        )
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 4}),
            "website": forms.URLInput(attrs={"placeholder": "https://"}),
        }


class ContactForm(forms.ModelForm):
    wide_fields = ("notes",)

    class Meta:
        model = Contact
        fields = (
            "first_name",
            "last_name",
            "job_title",
            "company",
            "kind",
            "email",
            "phone",
            "linkedin_url",
            "last_contacted_at",
            "notes",
        )
        widgets: ClassVar[dict[str, forms.Widget]] = {
            "last_contacted_at": DateTimeInput(),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }


class ContactFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=100)
    kind = forms.ChoiceField(
        choices=(("", "All kinds"), *ContactKind.choices), required=False, label="Kind"
    )

    def values(self) -> dict[str, Any]:
        self.is_valid()
        return {"search": self.cleaned_data.get("q") or "",
                "kind": self.cleaned_data.get("kind") or ""}  # fmt: skip
