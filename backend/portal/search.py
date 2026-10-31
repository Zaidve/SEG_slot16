from django.db.models import Q

from .models import Document


def search_documents(query, filters):
    """Return published documents matching a keyword and filters, best first.

    filters may hold 'category' and 'tag' slugs, and 'from' and 'to' dates.
    Phase 2 replaces this function with the hand-built search engine.
    """
    documents = (
        Document.objects.filter(status=Document.Status.PUBLISHED)
        .select_related('category', 'author')
        .prefetch_related('tags')
    )
    if query:
        documents = documents.filter(
            Q(title__icontains=query) | Q(content_text__icontains=query)
        )
    if filters.get('category'):
        documents = documents.filter(category__slug=filters['category'])
    if filters.get('tag'):
        documents = documents.filter(tags__slug=filters['tag'])
    if filters.get('from'):
        documents = documents.filter(published_at__date__gte=filters['from'])
    if filters.get('to'):
        documents = documents.filter(published_at__date__lte=filters['to'])
    return documents.order_by('-published_at', '-id')
