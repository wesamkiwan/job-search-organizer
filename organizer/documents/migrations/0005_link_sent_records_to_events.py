# Data migration ("backfill"): links sent records made BEFORE migration 0004 to their
# "Document sent" timeline entries.
#
# 0004 added ApplicationDocument.event, but only new records fill it. Older records have
# no link, so removing one would leave its timeline entry behind. Here we find each old
# record's entry: attach_version() created both with the same application and the same
# time (sent_at == occurred_at). We only link when there is EXACTLY ONE match, so we never
# guess (e.g. two documents recorded at the same moment stay unlinked).

from django.db import migrations


def link_sent_records_to_events(apps, schema_editor):
    ApplicationDocument = apps.get_model("documents", "ApplicationDocument")
    ApplicationEvent = apps.get_model("applications", "ApplicationEvent")
    for sent in ApplicationDocument.objects.filter(event__isnull=True):
        candidates = ApplicationEvent.objects.filter(
            application_id=sent.application_id,
            kind="document_sent",
            occurred_at=sent.sent_at,
            sent_document__isnull=True,  # not already linked to another record
        )
        # [:2] fetches at most two rows: enough to know "exactly one" or "more than one".
        matches = list(candidates[:2])
        if len(matches) == 1:
            sent.event = matches[0]
            sent.save(update_fields=["event"])


class Migration(migrations.Migration):

    dependencies = [
        ('applications', '0002_default_stages'),
        ('documents', '0004_applicationdocument_event'),
    ]

    operations = [
        # Going back needs nothing: migrating to 0003 removes the column itself.
        migrations.RunPython(link_sent_records_to_events, migrations.RunPython.noop),
    ]
