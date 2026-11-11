"""Phase 2: a hand-built search engine, ranked with BM25 over the inverted index."""
import math
from collections import Counter, defaultdict

from django.db.models import Avg

from .models import Document, IndexedDocument, Posting
from .text import parse_query

# Standard BM25 settings. K1 limits how much repeating a word helps,
# and B is how much a long field is marked down for being long.
K1 = 1.2
B = 0.75
# A word in the title counts three times as much as the same word in the body.
FIELD_WEIGHTS = {Posting.Field.TITLE: 3.0, Posting.Field.BODY: 1.0}


def search_documents(query, filters):
    """Return published documents matching a keyword and filters, best first.

    filters may hold 'category' and 'tag' slugs, and 'from' and 'to' dates.
    Without a keyword, filtered documents come newest first.
    """
    documents = filtered_documents(filters)
    if not query:
        return documents.order_by('-published_at', '-id')

    terms, phrases = parse_query(query)
    if not terms:  # nothing searchable, such as "%"
        return []
    scores = bm25_scores(terms, phrases)
    matches = documents.filter(pk__in=scores)
    # Ties go to the newer article, then the higher id, so the order never changes.
    return sorted(
        matches,
        key=lambda doc: (scores[doc.pk], doc.published_at.timestamp(), doc.pk),
        reverse=True,
    )


def filtered_documents(filters):
    documents = (
        Document.objects.filter(status=Document.Status.PUBLISHED)
        .select_related('category', 'author')
        .prefetch_related('tags')
    )
    if filters.get('category'):
        documents = documents.filter(category__slug=filters['category'])
    if filters.get('tag'):
        documents = documents.filter(tags__slug=filters['tag'])
    if filters.get('from'):
        documents = documents.filter(published_at__date__gte=filters['from'])
    if filters.get('to'):
        documents = documents.filter(published_at__date__lte=filters['to'])
    return documents


def bm25_scores(terms, phrases):
    """Score every document that holds all the terms and phrases. Returns {id: score}."""
    # found[document_id][term][field] = positions of the term in that field
    found = defaultdict(lambda: defaultdict(dict))
    for document_id, term, field, positions in Posting.objects.filter(
        term__in=terms
    ).values_list('document_id', 'term', 'field', 'positions'):
        found[document_id][term][field] = positions

    # How many documents contain each term. Rare terms say more about a match.
    doc_freq = Counter(term for by_term in found.values() for term in by_term)
    total = IndexedDocument.objects.count()
    idf = {
        term: math.log(1 + (total - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
        for term in terms
    }

    averages = IndexedDocument.objects.aggregate(
        title=Avg('title_length'), body=Avg('body_length')
    )
    average = {
        Posting.Field.TITLE: averages['title'] or 1,
        Posting.Field.BODY: averages['body'] or 1,
    }
    lengths = {
        entry['document_id']: {
            Posting.Field.TITLE: entry['title_length'],
            Posting.Field.BODY: entry['body_length'],
        }
        for entry in IndexedDocument.objects.filter(document_id__in=found).values(
            'document_id', 'title_length', 'body_length'
        )
    }

    scores = {}
    for document_id, by_term in found.items():
        if len(by_term) < len(terms):  # every term must appear
            continue
        if not all(has_phrase(by_term, phrase) for phrase in phrases):
            continue
        score = 0.0
        for term in terms:
            # BM25F: weigh and length-normalise each field, then add them up.
            weighted_tf = sum(
                FIELD_WEIGHTS[field] * len(positions)
                / (1 - B + B * lengths[document_id][field] / average[field])
                for field, positions in by_term[term].items()
            )
            score += idf[term] * weighted_tf / (K1 + weighted_tf)
        scores[document_id] = score
    return scores


def has_phrase(by_term, phrase):
    """True if the phrase's words sit next to each other in one field."""
    for field in FIELD_WEIGHTS:
        positions = [set(by_term[term].get(field, ())) for term in phrase]
        if any(
            all(start + offset in positions[offset] for offset in range(1, len(phrase)))
            for start in positions[0]
        ):
            return True
    return False
