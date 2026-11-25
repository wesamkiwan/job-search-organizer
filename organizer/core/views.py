from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import UserSettingsForm
from .models import UserSettings

# Design tokens shown as colour swatches in the UI gallery: (token name, Tailwind class).
# Full class names are written out so Tailwind finds them when it scans this file.
COLOR_TOKENS = [
    ("canvas", "bg-canvas"),
    ("surface", "bg-surface"),
    ("surface-muted", "bg-surface-muted"),
    ("line", "bg-line"),
    ("line-strong", "bg-line-strong"),
    ("line-input", "bg-line-input"),
    ("ink", "bg-ink"),
    ("ink-muted", "bg-ink-muted"),
    ("ink-subtle", "bg-ink-subtle"),
    ("accent", "bg-accent"),
    ("accent-hover", "bg-accent-hover"),
    ("accent-soft", "bg-accent-soft"),
    ("success", "bg-success"),
    ("warning", "bg-warning"),
    ("danger", "bg-danger"),
    ("info", "bg-info"),
]

# Made-up example rows for the table demo.
SAMPLE_APPLICATIONS = [
    {"company": "Nordlicht Software GmbH", "role": "Backend Developer (Python)", "city": "Hamburg",
     "applied": "18.11.2026", "status": "Interview", "tone": "accent"},
    {"company": "Rheinwerk Analytics AG", "role": "Data Engineer", "city": "Köln",
     "applied": "12.11.2026", "status": "Applied", "tone": "info"},
    {"company": "Alpenblick Systems", "role": "Django Developer", "city": "München",
     "applied": "03.11.2026", "status": "Offer", "tone": "success"},
    {"company": "Spreeufer Labs", "role": "Junior Software Engineer", "city": "Berlin",
     "applied": "28.10.2026", "status": "Rejected", "tone": "danger"},
]  # fmt: skip


def home(request: HttpRequest) -> HttpResponse:
    """Render the home page (dashboard)."""
    return render(request, "core/home.html")


def ui_gallery(request: HttpRequest) -> HttpResponse:
    """Show every UI component in one place (development only).

    A visual check for the design system: open it in light and dark mode after
    changing tokens or components. Returns 404 when DEBUG is off, so it never
    exists in production.
    """
    if not settings.DEBUG:
        raise Http404
    context = {"color_tokens": COLOR_TOKENS, "applications": SAMPLE_APPLICATIONS}
    return render(request, "core/ui_gallery.html", context)


def user_settings(request: HttpRequest) -> HttpResponse:
    """Show and save the app settings.

    Follows Post/Redirect/Get: after a successful save we redirect instead of rendering,
    so reloading the page doesn't submit the form a second time.
    """
    instance = UserSettings.load()
    if request.method == "POST":
        form = UserSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
            return redirect("core:settings")
    else:
        form = UserSettingsForm(instance=instance)
    context = {"form": form, "today": timezone.localdate()}
    return render(request, "core/settings.html", context)
