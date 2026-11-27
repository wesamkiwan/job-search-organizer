"""manage.py extract_document_text: (re)read the text of stored document versions.

New uploads get their text automatically. This command is for versions that have none
yet (e.g. uploaded before text extraction existed), or for all of them after the
extraction code was improved.

    uv run python manage.py extract_document_text         # versions without text
    uv run python manage.py extract_document_text --all   # every version
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from organizer.documents.extraction import extract_text
from organizer.documents.models import DocumentVersion


class Command(BaseCommand):
    help = "Extract the text of stored PDF and Word document versions."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--all", action="store_true", help="Also versions that have text.")

    def handle(self, *args: Any, **options: Any) -> None:
        versions = DocumentVersion.objects.select_related("document")
        if not options["all"]:
            versions = versions.filter(extracted_text="")

        updated = 0
        for version in versions:
            with version.file.open("rb") as file:
                text = extract_text(file, version.mime_type)
            if text != version.extracted_text:
                # update() writes just this one column, without calling save(): the
                # version's file and other fields stay exactly as they are.
                DocumentVersion.objects.filter(pk=version.pk).update(extracted_text=text)
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Text updated for {updated} version(s)."))
