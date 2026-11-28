"""Caching the widget data, so the dashboard stays fast as the data grows.

A widget's data is stored in Django's cache under a key made of:
  - a DATA VERSION: a number that goes up whenever data the dashboard reads changes,
  - the widget key,
  - the filters (the FilterContext, incl. "today", and the link parameters).

Invalidation ("when is the cached data outdated?") is the hard part of caching. Instead
of working out which widget a change affects, ANY save or delete of a model the
dashboard reads bumps the version (signals, connected in AnalyticsConfig.ready). Old
entries are then simply never asked for again and expire after TIMEOUT. A few extra cache
misses are cheap; showing outdated numbers is not.
"""

import hashlib
from typing import Any

from django.core.cache import cache

from .filters import FilterContext
from .widgets import Links, Widget

VERSION_KEY = "analytics:data-version"
TIMEOUT = 10 * 60  # seconds; also a safety net for changes no signal sees (e.g. .update())

# Apps whose models the dashboard reads. Saving a session or an admin log entry does not
# change any number, so those don't bump the version.
WATCHED_APPS = frozenset(
    {"applications", "companies", "core", "documents", "jobs", "sources", "analytics"}
)


def data_version() -> int:
    version = cache.get(VERSION_KEY)
    if version is None:
        version = 1
        cache.set(VERSION_KEY, version, None)  # None = never expires
    return int(version)


def bump(sender: type, **kwargs: Any) -> None:
    """Signal receiver: data changed, so all cached widget data is outdated."""
    if sender._meta.app_label in WATCHED_APPS:  # type: ignore[attr-defined]
        try:
            cache.incr(VERSION_KEY)
        except ValueError:  # the key doesn't exist yet (or was evicted)
            cache.set(VERSION_KEY, 2, None)


def _key(widget: Widget, ctx: FilterContext, links: Links) -> str:
    # repr() of the frozen dataclasses describes them completely; hashing keeps the key
    # short (cache backends limit key length).
    filters = repr((ctx, sorted(links.query.items())))
    digest = hashlib.sha256(filters.encode()).hexdigest()[:32]
    return f"analytics:{data_version()}:{widget.key}:{digest}"


def build(widget: Widget, ctx: FilterContext, links: Links) -> dict[str, Any]:
    """The widget's data, from the cache when possible."""
    key = _key(widget, ctx, links)
    data = cache.get(key)
    if data is None:
        data = widget.build(ctx, links)
        cache.set(key, data, TIMEOUT)
    return data  # type: ignore[no-any-return]
