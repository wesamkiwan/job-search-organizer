# Data migration: creates the default sources once, on every new database.
#
# A data migration changes ROWS, not the table structure. Created with
#   python manage.py makemigrations sources --empty --name default_sources
# and filled in by hand.

from django.db import migrations

DEFAULT_SOURCES = [
    # (name, kind, website)
    ("Manual", "manual", ""),
    ("StepStone", "manual", "https://www.stepstone.de"),
    ("LinkedIn", "manual", "https://www.linkedin.com/jobs"),
]


def create_default_sources(apps, schema_editor):
    # apps.get_model() returns the model AS IT WAS at this point in the migration
    # history. Never import the real model (from organizer.sources.models import Source):
    # it may get new fields later, and this old migration would break.
    Source = apps.get_model("sources", "Source")
    for name, kind, website in DEFAULT_SOURCES:
        # get_or_create: running it again (or on a database that has them) does nothing.
        Source.objects.get_or_create(name=name, defaults={"kind": kind, "website": website})


def delete_default_sources(apps, schema_editor):
    # The way back (python manage.py migrate sources 0001). Django first undoes every
    # migration that depends on this one (e.g. the job postings table), so nothing can
    # still point to these rows here.
    Source = apps.get_model("sources", "Source")
    Source.objects.filter(name__in=[name for name, _, _ in DEFAULT_SOURCES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('sources', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_default_sources, delete_default_sources),
    ]
