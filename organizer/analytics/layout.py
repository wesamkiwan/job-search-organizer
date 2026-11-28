"""The dashboard layout: which widgets, in which order and size.

The stored layout (DashboardLayout) is only a wish list: whatever it says, only widgets
that exist in the registry are shown, each at most once, with a valid size. That keeps
the page working when a widget is renamed or removed from the code, and when the JSON
was edited by hand in the admin.
"""

from dataclasses import dataclass
from typing import Any

from .models import DashboardLayout
from .widgets import DEFAULT_LAYOUT, WIDGETS

SIZES = ("half", "full")


@dataclass(frozen=True)
class Placement:
    key: str
    size: str


def current() -> DashboardLayout:
    layout, _created = DashboardLayout.objects.get_or_create(name="Default")
    return layout


def placements(layout: DashboardLayout | None = None) -> list[Placement]:
    """The widgets to show, in order: the saved ones, then any NEW widget (in neither the
    saved list nor the hidden list) with its default size."""
    layout = layout or current()
    hidden = {key for key in layout.hidden if isinstance(key, str)}
    result: list[Placement] = []
    seen: set[str] = set()
    for entry in layout.widgets if isinstance(layout.widgets, list) else []:
        key = entry.get("key") if isinstance(entry, dict) else None
        if key in WIDGETS and key not in seen and key not in hidden:
            size = entry.get("size")
            result.append(Placement(key, size if size in SIZES else WIDGETS[key].size))
            seen.add(key)
    for key in (*DEFAULT_LAYOUT, *WIDGETS):  # registry order for widgets not in the default
        if key in WIDGETS and key not in seen and key not in hidden:
            result.append(Placement(key, WIDGETS[key].size))
            seen.add(key)
    return result


def hidden_widgets(layout: DashboardLayout | None = None) -> list[str]:
    """Registered widgets that are not shown (for the "Add a widget" menu)."""
    shown = {p.key for p in placements(layout)}
    return [key for key in WIDGETS if key not in shown]


class LayoutError(ValueError):
    """The layout sent by the browser is not valid."""


def save(widgets: Any) -> DashboardLayout:
    """Save the order and sizes sent by the browser after a drag, resize or remove.

    Every registered widget that is not in the list counts as hidden. Anything invalid
    (unknown key, duplicate, wrong size, wrong shape) is refused as a whole, so a broken
    request can't half-change the layout.
    """
    if not isinstance(widgets, list):
        raise LayoutError("Expected a list of widgets.")
    cleaned: list[dict[str, str]] = []
    for entry in widgets:
        if not isinstance(entry, dict):
            raise LayoutError("Each widget must be an object with key and size.")
        key, size = entry.get("key"), entry.get("size")
        if key not in WIDGETS:
            raise LayoutError(f"Unknown widget: {key!r}.")
        if size not in SIZES:
            raise LayoutError(f"Unknown size: {size!r}.")
        if any(item["key"] == key for item in cleaned):
            raise LayoutError(f"Widget {key!r} appears twice.")
        cleaned.append({"key": str(key), "size": str(size)})
    layout = current()
    layout.widgets = cleaned
    layout.hidden = [key for key in WIDGETS if all(item["key"] != key for item in cleaned)]
    layout.save()
    return layout


def show(key: str) -> None:
    """Add a hidden widget back, at the end."""
    if key not in WIDGETS:
        raise LayoutError(f"Unknown widget: {key!r}.")
    entries = [{"key": p.key, "size": p.size} for p in placements()]
    if all(entry["key"] != key for entry in entries):
        entries.append({"key": key, "size": WIDGETS[key].size})
    save(entries)


def reset() -> None:
    """Back to the default layout (order, sizes, nothing hidden)."""
    layout = current()
    layout.widgets, layout.hidden = [], []
    layout.save()
