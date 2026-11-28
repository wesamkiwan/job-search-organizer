# Data migration: gives the default stages their dashboard roles.
#
# "Interviewing" counts as an interview, "Ghosted" as ghosted. The stages are found by
# their category AND their default name: if you renamed or deleted them, nothing happens
# (you can switch the roles on in the admin instead). Running it again changes nothing.

from django.db import migrations

ROLES = [
    # (category, name, field)
    ("in_progress", "Interviewing", "counts_as_interview"),
    ("lost", "Ghosted", "counts_as_ghosted"),
]


def set_default_roles(apps, schema_editor):
    PipelineStage = apps.get_model("applications", "PipelineStage")
    for category, name, field in ROLES:
        PipelineStage.objects.filter(category=category, name=name).update(**{field: True})


def unset_default_roles(apps, schema_editor):
    PipelineStage = apps.get_model("applications", "PipelineStage")
    for category, name, field in ROLES:
        PipelineStage.objects.filter(category=category, name=name).update(**{field: False})


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0003_stage_roles'),
    ]

    operations = [
        migrations.RunPython(set_default_roles, unset_default_roles),
    ]
