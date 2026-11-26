# Data migration: the default pipeline stages (docs/02-data-model.md, "PipelineStage").
# You can rename, recolour and reorder them later; the app only relies on the category.

from django.db import migrations

DEFAULT_STAGES = [
    # (order, name, category, color, is_default_for_category)
    (10, "Saved", "saved", "neutral", True),
    (20, "Applied", "applied", "info", True),
    (30, "Screening", "in_progress", "info", True),
    (40, "Interviewing", "in_progress", "accent", False),
    (50, "Offer", "offer", "warning", True),
    (60, "Accepted", "won", "success", True),
    (70, "Rejected", "lost", "danger", True),
    (80, "Ghosted", "lost", "neutral", False),
    (90, "Withdrawn", "withdrawn", "neutral", True),
]


def create_default_stages(apps, schema_editor):
    PipelineStage = apps.get_model("applications", "PipelineStage")
    for order, name, category, color, is_default in DEFAULT_STAGES:
        PipelineStage.objects.get_or_create(
            name=name,
            defaults={
                "order": order,
                "category": category,
                "color": color,
                "is_default_for_category": is_default,
            },
        )


def delete_default_stages(apps, schema_editor):
    PipelineStage = apps.get_model("applications", "PipelineStage")
    PipelineStage.objects.filter(name__in=[stage[1] for stage in DEFAULT_STAGES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_default_stages, delete_default_stages),
    ]
