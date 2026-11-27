"""Write operations for applications: the ONLY place where an application's stage changes.

Why a service layer? Changing a stage is more than `application.stage = x; save()`.
Several things must happen together, every time, wherever the change comes from (a form,
the kanban board, the admin, a future import):

  - a timeline event is written (from which stage to which, when)
  - applied_on is filled when the application leaves "Saved"
  - closed_at / outcome_stage are set when a final stage is reached (and cleared on reopen)
  - the posting's triage status follows (saved / applied)

Putting these rules in one place means they can't be forgotten, and they are unit tested.
Each function runs inside a database transaction: either everything is saved, or nothing.
"""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from organizer.jobs.models import TriageStatus

from .models import Application, ApplicationEvent, EventKind, PipelineStage, StageCategory


class ApplicationError(Exception):
    """A business rule was broken. The message is meant for the user (views show it)."""


def default_stage(category: StageCategory) -> PipelineStage:
    """The default stage of a category, e.g. Rejected for LOST."""
    return PipelineStage.objects.get(category=category, is_default_for_category=True)


@transaction.atomic
def create_application(
    application: Application, *, occurred_at: datetime | None = None
) -> Application:
    """Save a NEW application and start its timeline.

    `application` is an unsaved object, e.g. from `form.save(commit=False)`. If it has no
    stage yet, it starts in the default "applied" stage.
    """
    if application.pk is not None:
        raise ApplicationError("This application is already saved.")
    if Application.objects.filter(posting_id=application.posting_id).exists():
        raise ApplicationError("This job posting already has an application.")
    when = _check_time(occurred_at)

    if application.stage_id is None:
        application.stage = default_stage(StageCategory.APPLIED)
    to_stage = application.stage

    _enter_stage(application, from_stage=None, to_stage=to_stage, when=when)
    application.save()
    _record_stage_change(application, None, to_stage, when, summary=f"Created in “{to_stage}”")
    _sync_posting_status(application)
    return application


@transaction.atomic
def change_stage(
    application: Application,
    to_stage: PipelineStage,
    *,
    occurred_at: datetime | None = None,
    note: str = "",
) -> ApplicationEvent:
    """Move an application to another stage and record it on the timeline.

    occurred_at can be in the past ("they rejected me last Friday"), not in the future.
    """
    if to_stage.pk == application.stage_id:
        raise ApplicationError(f"The application is already in “{to_stage}”.")
    when = _check_time(occurred_at)
    # The timeline must stay in order: a stage change can't be dated before the last one.
    last_change = (
        application.events.filter(kind=EventKind.STAGE_CHANGE).order_by("-occurred_at").first()
    )
    # Compared by the minute: forms send "14:05", while the last change may be 14:05:33.
    if last_change is not None and when < last_change.occurred_at.replace(second=0, microsecond=0):
        last = timezone.localtime(last_change.occurred_at).strftime("%d.%m.%Y %H:%M")
        raise ApplicationError(f"The date can't be before the last stage change ({last}).")
    from_stage = application.stage

    _enter_stage(application, from_stage=from_stage, to_stage=to_stage, when=when)
    application.stage = to_stage
    application.save()
    event = _record_stage_change(
        application, from_stage, to_stage, when, summary=f"{from_stage} → {to_stage}", note=note
    )
    _sync_posting_status(application)
    return event


@transaction.atomic
def close_application(
    application: Application,
    *,
    stage: PipelineStage | None = None,
    reason: str = "",
    details: str = "",
    occurred_at: datetime | None = None,
) -> ApplicationEvent:
    """End an application: rejected (the default), ghosted, withdrawn or accepted.

    reason/details (a RejectionReason value + free text) only fit a "lost" stage.
    """
    if application.is_closed:
        raise ApplicationError("The application is already closed.")
    stage = stage or default_stage(StageCategory.LOST)
    if not stage.is_final:
        raise ApplicationError(f"“{stage}” is not a final stage.")
    if (reason or details) and stage.category != StageCategory.LOST:
        raise ApplicationError("A rejection reason only fits a lost application.")

    application.rejection_reason = reason
    application.rejection_details = details
    # change_stage saves the application (with the reason) and writes the event. It has
    # its own @transaction.atomic; nested inside ours it simply joins this transaction.
    return change_stage(application, stage, occurred_at=occurred_at)


def add_event(
    application: Application,
    *,
    kind: str,
    summary: str,
    details: str = "",
    occurred_at: datetime | None = None,
) -> ApplicationEvent:
    """Add a note, call, email, ... to the timeline (anything except a stage change)."""
    if kind == EventKind.STAGE_CHANGE:
        raise ApplicationError("Stage changes are recorded by changing the stage.")
    if not summary.strip():
        raise ApplicationError("Please write a short summary.")
    when = _check_time(occurred_at)
    event = ApplicationEvent.objects.create(
        application=application, kind=kind, summary=summary.strip(), details=details,
        occurred_at=when,
    )  # fmt: skip
    # New activity counts as an update (the list's "Updated" column sorts by it).
    # update() changes only this column, without loading or saving the whole object.
    Application.objects.filter(pk=application.pk).update(updated_at=timezone.now())
    return event


@transaction.atomic
def delete_application(application: Application) -> None:
    """Delete an application and its timeline and tasks. The job posting stays (as saved)."""
    posting = application.posting
    application.delete()  # events and tasks go too (CASCADE)
    posting.triage_status = TriageStatus.SAVED
    posting.save(update_fields=("triage_status", "updated_at"))


# --- helpers (the leading underscore means: only for use inside this module) -------------


def _check_time(occurred_at: datetime | None) -> datetime:
    now = timezone.now()
    if occurred_at is None:
        return now
    if occurred_at > now:
        raise ApplicationError("The date can't be in the future.")
    return occurred_at


def _enter_stage(
    application: Application,
    *,
    from_stage: PipelineStage | None,
    to_stage: PipelineStage,
    when: datetime,
) -> None:
    """Update the fields that depend on the stage (without saving)."""
    if to_stage.category != StageCategory.SAVED and application.applied_on is None:
        application.applied_on = timezone.localdate(when)

    if to_stage.is_final:
        application.closed_at = when
        # For analytics: how far did a lost application get before it was lost? Moving
        # between final stages (Rejected → Ghosted) keeps the stage from before the end.
        was_open = from_stage is None or not from_stage.is_final
        if to_stage.category == StageCategory.LOST and was_open:
            application.outcome_stage = from_stage
    else:
        # Reopened (e.g. "Rejected" was a mistake): it isn't closed any more.
        application.closed_at = None
        application.outcome_stage = None
        application.rejection_reason = ""
        application.rejection_details = ""


def _record_stage_change(
    application: Application,
    from_stage: PipelineStage | None,
    to_stage: PipelineStage,
    when: datetime,
    *,
    summary: str,
    note: str = "",
) -> ApplicationEvent:
    return ApplicationEvent.objects.create(
        application=application,
        kind=EventKind.STAGE_CHANGE,
        from_stage=from_stage,
        to_stage=to_stage,
        occurred_at=when,
        summary=summary,
        details=note,
    )


def _sync_posting_status(application: Application) -> None:
    """Saved applications mark their posting "saved", all others "applied"."""
    posting = application.posting
    if application.stage.category == StageCategory.SAVED:
        posting.triage_status = TriageStatus.SAVED
    else:
        posting.triage_status = TriageStatus.APPLIED
    # update_fields: write only these columns (faster, and doesn't overwrite other
    # changes). updated_at must be listed, or auto_now wouldn't be saved.
    posting.save(update_fields=("triage_status", "updated_at"))
