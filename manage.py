#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main() -> None:
    """Run administrative tasks."""
    # Local development settings by default; override with the DJANGO_SETTINGS_MODULE variable.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Did you run 'uv sync' and start the command with 'uv run'?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
