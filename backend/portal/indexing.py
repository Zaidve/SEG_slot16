"""Keep the inverted index in step with published documents."""
from collections import defaultdict

from django.db import transaction

from .models import Document, IndexedDocument, Posting
from .text import analyze


def document_fields(document):
    # The summary is part of the body: it is the article's own short version.
    return {
        Posting.Field.TITLE: document.title,
        Posting.Field.BODY: f'{document.summary} {document.content_text}',
    }


@transaction.atomic
def index_document(document):
    """Index a published document. Anything else is removed from the index."""
    remove_document(document)
    if document.status != Document.Status.PUBLISHED:
        return

    lengths = {}
    postings = []
    for field, text in document_fields(document).items():
        terms = analyze(text)
        lengths[field] = len(terms)
        positions = defaultdict(list)
        for position, term in enumerate(terms):
            positions[term].append(position)
        postings += [
            Posting(document=document, field=field, term=term, tf=len(found), positions=found)
            for term, found in positions.items()
        ]

    IndexedDocument.objects.create(
        document=document,
        title_length=lengths[Posting.Field.TITLE],
        body_length=lengths[Posting.Field.BODY],
    )
    Posting.objects.bulk_create(postings)


def remove_document(document):
    IndexedDocument.objects.filter(document=document).delete()
    Posting.objects.filter(document=document).delete()


@transaction.atomic
def rebuild_index():
    """Index every published document from scratch. Returns how many."""
    IndexedDocument.objects.all().delete()
    Posting.objects.all().delete()
    documents = Document.objects.filter(status=Document.Status.PUBLISHED)
    for document in documents:
        index_document(document)
    return documents.count()
