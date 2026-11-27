"""Read queries for documents (the write operations are in services.py)."""

from django.db.models import Count, Max, Q, QuerySet

from .models import Document, DocumentLanguage, DocumentType, DocumentVersion


def document_list(
    search: str = "",
    document_type: DocumentType | None = None,
    language: str = "",
    show_archived: bool = False,
) -> QuerySet[Document]:
    """Documents grouped by type, A to Z, with their version count, last upload and the
    number of applications they were sent with.

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
    sent with (sent_count)."""
    return document.versions.annotate(
        sent_count=Count("sent_with__application", distinct=True)
    ).order_by("-version_number")
