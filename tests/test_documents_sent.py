"""Recording which document versions were sent with an application (step 2.5)."""

import importlib
from datetime import datetime, timedelta

import pytest
from django import forms
from django.apps import apps as django_apps
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import assertContains, assertNotContains

from organizer.applications.models import Application, ApplicationEvent, EventKind
from organizer.core.models import UserSettings
from organizer.documents import services
from organizer.documents.forms import SendDocumentForm
from organizer.documents.models import ApplicationDocument
from organizer.documents.selectors import sendable_versions, sent_documents_for
from tests.factories import (
    ApplicationDocumentFactory,
    ApplicationFactory,
    DocumentFactory,
    DocumentVersionFactory,
)

pytestmark = pytest.mark.django_db


def as_input(moment: datetime) -> str:
    """A datetime in the format of a datetime-local input (what the browser sends)."""
    return timezone.localtime(moment).strftime("%Y-%m-%dT%H:%M")


# --- services ----------------------------------------------------------------------------


def test_attach_links_the_timeline_event() -> None:
    sent = services.attach_version(ApplicationFactory.create(), DocumentVersionFactory.create())
    assert sent.event is not None
    assert sent.event.kind == EventKind.DOCUMENT_SENT


def test_detach_removes_the_record_and_its_event() -> None:
    application = ApplicationFactory.create()
    sent = services.attach_version(application, DocumentVersionFactory.create())
    services.detach_version(sent)
    assert not ApplicationDocument.objects.exists()
    assert not application.events.exists()
    # The version is free again: it can now be deleted.
    services.delete_version(sent.document_version)


def test_detach_without_an_event() -> None:
    # Records made directly (e.g. by an import) may have no linked event.
    sent = ApplicationDocumentFactory.create()
    services.detach_version(sent)
    assert not ApplicationDocument.objects.exists()


def test_deleting_the_event_keeps_the_record() -> None:
    sent = services.attach_version(ApplicationFactory.create(), DocumentVersionFactory.create())
    assert sent.event is not None
    sent.event.delete()
    sent.refresh_from_db()
    assert sent.event is None  # on_delete=SET_NULL


# --- selectors and form ------------------------------------------------------------------


def test_sendable_versions_skip_archived_and_already_sent() -> None:
    application = ApplicationFactory.create()
    cv = DocumentFactory.create(title="A CV")
    v1, v2 = DocumentVersionFactory.create_batch(2, document=cv)
    letter = DocumentVersionFactory.create(document__title="B letter")
    DocumentVersionFactory.create(document__is_archived=True)
    ApplicationDocumentFactory.create(application=application, document_version=v1)

    # By document title, newest version first.
    assert list(sendable_versions(application)) == [v2, letter]
    # Sent with ANOTHER application doesn't matter here.
    assert list(sendable_versions(ApplicationFactory.create())) == [v2, v1, letter]


def test_form_labels_name_document_version_and_file() -> None:
    version = DocumentVersionFactory.create(document__title="CV EN", original_filename="cv.pdf")
    field = SendDocumentForm(application=ApplicationFactory.create()).fields["version"]
    assert isinstance(field, forms.ModelChoiceField)  # tells mypy which kind of field it is
    assert field.queryset is not None
    assert list(field.queryset) == [version]
    assert field.label_from_instance(version) == "CV EN · v1 · cv.pdf"


def test_sent_documents_for_newest_first() -> None:
    application = ApplicationFactory.create()
    now = timezone.now()
    old = ApplicationDocumentFactory.create(application=application, sent_at=now - timedelta(1))
    new = ApplicationDocumentFactory.create(application=application, sent_at=now)
    ApplicationDocumentFactory.create()  # another application
    assert list(sent_documents_for(application)) == [new, old]


# --- the card on the application page ----------------------------------------------------


def test_application_page_lists_sent_documents_and_the_form(admin_client: Client) -> None:
    application = ApplicationFactory.create()
    sent = ApplicationDocumentFactory.create(
        application=application, document_version__document__title="CV - Backend (EN)"
    )
    DocumentVersionFactory.create(document__title="Cover letter ACME")
    response = admin_client.get(application.get_absolute_url())

    assertContains(response, "Documents sent")
    assertContains(response, "CV - Backend (EN)")
    assertContains(response, f'id="remove-sent-{sent.pk}"')
    assertContains(response, "Cover letter ACME · v1")  # can still be recorded
    assertContains(response, reverse("documents:send", args=[application.pk]))


def test_application_page_without_documents(admin_client: Client) -> None:
    response = admin_client.get(ApplicationFactory.create().get_absolute_url())
    assertContains(response, "None recorded yet.")
    assertContains(response, "No documents yet.")
    assertNotContains(response, "Record as sent")


def test_application_page_when_everything_was_sent(admin_client: Client) -> None:
    sent = ApplicationDocumentFactory.create()
    response = admin_client.get(sent.application.get_absolute_url())
    assertContains(response, "All your document versions are recorded here.")


def test_record_as_sent(admin_client: Client) -> None:
    application = ApplicationFactory.create()
    version = DocumentVersionFactory.create(document__title="CV EN")
    yesterday = timezone.now() - timedelta(days=1)
    response = admin_client.post(
        reverse("documents:send", args=[application.pk]),
        {"version": version.pk, "sent_at": as_input(yesterday)},
        follow=True,
    )
    assertContains(response, "“CV EN v1” recorded as sent.")
    sent = ApplicationDocument.objects.get()
    assert sent.sent_at.date() == timezone.localtime(yesterday).date()
    assertContains(response, "Sent “CV EN v1”")  # the timeline entry


def test_record_as_sent_errors(admin_client: Client) -> None:
    application = ApplicationFactory.create()
    version = DocumentVersionFactory.create()
    url = reverse("documents:send", args=[application.pk])

    tomorrow = timezone.now() + timedelta(days=1)
    response = admin_client.post(
        url, {"version": version.pk, "sent_at": as_input(tomorrow)}, follow=True
    )
    assertContains(response, "The date can&#x27;t be in the future.")

    response = admin_client.post(url, {"sent_at": as_input(timezone.now())}, follow=True)
    assertContains(response, "Document: This field is required.")
    assert not ApplicationDocument.objects.exists()


def test_recording_the_same_version_twice_is_refused(admin_client: Client) -> None:
    sent = ApplicationDocumentFactory.create()
    response = admin_client.post(
        reverse("documents:send", args=[sent.application_id]),
        {"version": sent.document_version_id, "sent_at": as_input(timezone.now())},
        follow=True,
    )
    # It isn't offered any more, so the form refuses it as an invalid choice.
    assertContains(response, "Select a valid choice.")
    assert ApplicationDocument.objects.count() == 1


def test_service_error_becomes_a_message(
    admin_client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise services.DocumentError("Something went wrong.")

    monkeypatch.setattr(services, "attach_version", fail)
    application = ApplicationFactory.create()
    response = admin_client.post(
        reverse("documents:send", args=[application.pk]),
        {"version": DocumentVersionFactory.create().pk, "sent_at": as_input(timezone.now())},
        follow=True,
    )
    assertContains(response, "Something went wrong.")


def test_remove_a_sent_document(admin_client: Client) -> None:
    application = ApplicationFactory.create()
    sent = services.attach_version(
        application, DocumentVersionFactory.create(document__title="CV EN")
    )
    response = admin_client.post(reverse("documents:remove_sent", args=[sent.pk]), follow=True)
    assertContains(response, "“CV EN v1” is no longer recorded as sent.")
    assert not ApplicationDocument.objects.exists()
    assert not application.events.exists()


def test_send_and_remove_need_post(admin_client: Client) -> None:
    sent = ApplicationDocumentFactory.create()
    assert (
        admin_client.get(reverse("documents:send", args=[sent.application_id])).status_code == 405
    )
    assert admin_client.get(reverse("documents:remove_sent", args=[sent.pk])).status_code == 405


def test_admin_delete_removes_the_timeline_entry(admin_client: Client) -> None:
    application = ApplicationFactory.create()
    first = services.attach_version(application, DocumentVersionFactory.create())
    second = services.attach_version(application, DocumentVersionFactory.create())
    admin_client.post(
        reverse("admin:documents_applicationdocument_delete", args=[first.pk]), {"post": "yes"}
    )
    admin_client.post(
        reverse("admin:documents_applicationdocument_changelist"),
        {"action": "delete_selected", "_selected_action": [second.pk], "post": "yes"},
    )
    assert not ApplicationDocument.objects.exists()
    assert not application.events.exists()


# --- "used in" on the document page (step 2.6) -------------------------------------------


def test_document_page_shows_where_each_version_was_used(admin_client: Client) -> None:
    document = DocumentFactory.create()
    used = DocumentVersionFactory.create(document=document)
    DocumentVersionFactory.create(document=document)  # v2, never sent
    sent = ApplicationDocumentFactory.create(
        document_version=used,
        application__posting__title="Python Developer",
        application__posting__company__name="Nordlicht Software GmbH",
    )
    response = admin_client.get(document.get_absolute_url())
    assertContains(response, "Used in", count=1)  # only under v1
    assertContains(response, "Python Developer")
    assertContains(response, "Nordlicht Software GmbH · sent")
    assertContains(response, sent.application.get_absolute_url())
    assertContains(response, sent.application.stage.name)


def test_used_in_needs_the_same_queries_for_any_number_of_versions(
    admin_client: Client,
) -> None:
    """Thanks to the prefetch, more versions and more sent records don't mean more
    queries (no "N+1 problem": one query per version would grow with N)."""

    def count_queries(document_pk: int) -> int:
        url = reverse("documents:detail", args=[document_pk])
        with CaptureQueriesContext(connection) as queries:
            admin_client.get(url)
        return len(queries)

    # The very first request also creates the settings row (UserSettings.load() =
    # get_or_create), which would add queries to whichever page is measured first.
    UserSettings.load()
    small = DocumentFactory.create()
    ApplicationDocumentFactory.create(document_version__document=small)
    big = DocumentFactory.create()
    for version in DocumentVersionFactory.create_batch(4, document=big):
        ApplicationDocumentFactory.create_batch(2, document_version=version)

    assert count_queries(big.pk) == count_queries(small.pk)


# --- migration 0005: backfill the event links of older records ---------------------------

# A module name can't start with a digit in an import statement, so importlib loads it.
backfill = importlib.import_module(
    "organizer.documents.migrations.0005_link_sent_records_to_events"
).link_sent_records_to_events


def old_style_send(application: Application, when: datetime) -> ApplicationDocument:
    """What attach_version() wrote before migration 0004: a record + event, NOT linked."""
    ApplicationEvent.objects.create(
        application=application, kind=EventKind.DOCUMENT_SENT, occurred_at=when
    )
    return ApplicationDocumentFactory.create(application=application, sent_at=when)


def test_backfill_links_the_one_matching_event() -> None:
    application = ApplicationFactory.create()
    when = timezone.now() - timedelta(days=3)
    sent = old_style_send(application, when)
    # Distractors: a note at the same time, and a "sent" event at another time.
    ApplicationEvent.objects.create(application=application, kind=EventKind.NOTE, occurred_at=when)
    ApplicationEvent.objects.create(
        application=application, kind=EventKind.DOCUMENT_SENT, occurred_at=when - timedelta(1)
    )

    backfill(django_apps, None)  # the real app registry stands in for the migration's

    sent.refresh_from_db()
    assert sent.event is not None
    assert (sent.event.kind, sent.event.occurred_at) == (EventKind.DOCUMENT_SENT, when)


def test_backfill_does_not_guess_when_ambiguous() -> None:
    # Two documents recorded at the same moment: two records, two identical events.
    application = ApplicationFactory.create()
    when = timezone.now()
    first = old_style_send(application, when)
    second = old_style_send(application, when)
    backfill(django_apps, None)
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.event is None and second.event is None


def test_backfill_skips_linked_records_and_events() -> None:
    linked = services.attach_version(ApplicationFactory.create(), DocumentVersionFactory.create())
    # An old record at the same time as the linked event: that event is taken.
    orphan = ApplicationDocumentFactory.create(
        application=linked.application, sent_at=linked.sent_at
    )
    backfill(django_apps, None)
    orphan.refresh_from_db()
    assert orphan.event is None
    assert ApplicationDocument.objects.get(pk=linked.pk).event_id == linked.event_id
