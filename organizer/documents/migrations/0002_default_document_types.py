# Data migration: creates the default document types once, on every new database.
# (Same pattern as sources/0002_default_sources.py and applications/0002_default_stages.py.)

from django.db import migrations

DEFAULT_DOCUMENT_TYPES = [
    # (name, description, order) - gaps of 10 leave room to insert a type later
    ("CV", "Lebenslauf", 10),
    ("Cover letter", "Anschreiben", 20),
    ("Reference letter", "Arbeitszeugnis", 30),
    ("Certificate", "Zertifikat, diploma, transcript", 40),
    ("Portfolio", "Work samples", 50),
    ("Photo", "Bewerbungsfoto", 60),
    ("Other", "", 70),
]


def create_default_document_types(apps, schema_editor):
    # The historical model, as it was at this point of the migrations (never import it).
    DocumentType = apps.get_model("documents", "DocumentType")
    for name, description, order in DEFAULT_DOCUMENT_TYPES:
        DocumentType.objects.get_or_create(
            name=name, defaults={"description": description, "order": order}
        )


def delete_default_document_types(apps, schema_editor):
    DocumentType = apps.get_model("documents", "DocumentType")
    DocumentType.objects.filter(name__in=[name for name, _, _ in DEFAULT_DOCUMENT_TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_default_document_types, delete_default_document_types),
    ]
