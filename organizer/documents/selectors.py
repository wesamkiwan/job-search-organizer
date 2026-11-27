"""Read queries for documents (the write operations are in services.py)."""

from django.db.models import Count, Max, OuterRef, Prefetch, Q, QuerySet, Subquery

from organizer.applications.models import Application

from .models import ApplicationDocument, Document, DocumentLanguage, DocumentType, DocumentVersion


def document_list(
    search: str = "",
    document_type: DocumentType | None = None,
    language: str = "",
    show_archived: bool = False,
) -> QuerySet[Document]:
    """Documents grouped by type, A to Z, with their version count, last upload, the pages
    of their latest version and the number of applications they were sent with.

    The search also looks INSIDE the files (their extracted text) and at file names.
    """
    documents = (
        Document.objects.select_related("document_type")
        .prefetch_related("tags")
        .annotate(
            # distinct=True: these Counts go over two levels of relations (document →
            # versions → sent records); without it, rows would be counted several times.
            version_count=Count("versions", distinct=True),
            sent_count=Count("versions__sent_with__application", distinct=True),
            last_upload_at=Max("versions__created_at"),
            # A subquery per row: "the page_count of this document's newest version".
            # OuterRef("pk") refers to the document of the outer query (the row being
            # built). [:1] = LIMIT 1, so the subquery returns one value.
            latest_page_count=Subquery(
                DocumentVersion.objects.filter(document=OuterRef("pk"))
                .order_by("-version_number")
                .values("page_count")[:1]
            ),
        )
    )
    if not show_archived:
        documents = documents.filter(is_archived=False)
    if document_type is not None:
        documents = documents.filter(document_type=document_type)
    if language in DocumentLanguage.values:
        documents = documents.filter(language=language)
    if search := search.strip():
        # Why "pk__in" (a subquery) instead of Q(versions__extracted_text__icontains=...)?
        # Filtering through a "many" relation JOINs it again: a document with 3 matching
        # versions would appear 3 times AND its counts above would be multiplied. A
        # subquery ("documents whose id is in this list") changes neither.
        in_files = DocumentVersion.objects.filter(
            Q(extracted_text__icontains=search)
            | Q(original_filename__icontains=search)
            | Q(change_notes__icontains=search)
        ).values("document")
        with_tag = Document.objects.filter(tags__name__icontains=search).values("pk")
        documents = documents.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(pk__in=in_files)
            | Q(pk__in=with_tag)
        )
    return documents.order_by("document_type__order", "title", "pk")


def versions_of(document: Document) -> QuerySet[DocumentVersion]:
    """A document's versions, newest first, each with the number of applications it was
    sent with (sent_count) and those records ("used in"), newest first.

    prefetch_related + Prefetch: ONE extra query loads the sent records of ALL versions
    (with their applications, postings, companies and stages), instead of one query per
    version. Prefetch() lets us choose that query's select_related and ordering.
    """
    sent_records = ApplicationDocument.objects.select_related(
        "application__posting__company", "application__stage"
    ).order_by("-sent_at", "-pk")
    return (
        document.versions.annotate(sent_count=Count("sent_with__application", distinct=True))
        .prefetch_related(Prefetch("sent_with", queryset=sent_records))
        .order_by("-version_number")
    )


def sent_documents_for(application: Application) -> QuerySet[ApplicationDocument]:
    """The document versions sent with an application, newest first."""
    return (
        ApplicationDocument.objects.filter(application=application)
        .select_related("document_version__document__document_type")
        .order_by("-sent_at", "-pk")
    )


def sendable_versions(application: Application) -> QuerySet[DocumentVersion]:
    """Versions that can still be recorded as sent with this application: those of
    documents that are not archived, minus the ones already sent with it.
    Grouped by document, newest version first."""
    return (
        DocumentVersion.objects.filter(document__is_archived=False)
        .exclude(sent_with__application=application)
        .select_related("document")
        .order_by("document__title", "document_id", "-version_number")
    )
