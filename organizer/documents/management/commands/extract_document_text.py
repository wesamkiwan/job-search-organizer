"""manage.py extract_document_text: (re)read the text and page count of stored versions.

New uploads get both automatically. This command is for versions that have no text or
no page count yet (e.g. uploaded before this existed), or for all of them after the
reading code was improved.

    uv run python manage.py extract_document_text         # versions missing text or pages
    uv run python manage.py extract_document_text --all   # every version
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db.models import Q

from organizer.documents.extraction import read_contents
from organizer.documents.models import DocumentVersion


class Command(BaseCommand):
    help = "Read the text and page count of stored document versions."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--all", action="store_true", help="Every version, not only gaps.")

    def handle(self, *args: Any, **options: Any) -> None:
        versions = DocumentVersion.objects.all()
        if not options["all"]:
            versions = versions.filter(Q(extracted_text="") | Q(page_count__isnull=True))

        updated = 0
        for version in versions:
            with version.file.open("rb") as file:
                contents = read_contents(file, version.mime_type)
            if (contents.text, contents.page_count) != (version.extracted_text, version.page_count):
                # update() writes just these columns, without calling save(): the
                # version's file and other fields stay exactly as they are.
                DocumentVersion.objects.filter(pk=version.pk).update(
                    extracted_text=contents.text, page_count=contents.page_count
                )
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} version(s)."))
