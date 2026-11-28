"""Fixtures that pytest makes available to every test file in this folder.

conftest.py is a special file name: pytest loads it automatically, nobody imports it.
"""

from pathlib import Path

import pytest
from django.core.cache import cache
from pytest_django import Settings


@pytest.fixture(autouse=True)
def media_root(settings: Settings, tmp_path: Path) -> Path:
    """Store uploaded files in a temporary folder, never in the real media/ folder.

    autouse=True: every test gets this fixture without asking for it. tmp_path is a
    pytest fixture: a new, empty folder for each test, cleaned up by pytest later.
    Changing settings.MEDIA_ROOT here is undone automatically after the test.
    """
    folder = tmp_path / "media"
    settings.MEDIA_ROOT = folder
    return folder


@pytest.fixture(autouse=True)
def empty_cache() -> None:
    """Start every test with an empty cache (the dashboard caches widget data).

    The test database is rolled back after each test WITHOUT "deleted" signals, so the
    cache's data version wouldn't notice; old entries could leak into the next test.
    """
    cache.clear()
