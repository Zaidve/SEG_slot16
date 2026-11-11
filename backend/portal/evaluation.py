"""Measure search quality against hand-judged queries in seed/search_judgments.json.

Grades: 3 = highly relevant, 2 = relevant, 1 = marginal, missing = not relevant.
"""
import json
import math
from pathlib import Path

from django.db.models import Q

from .search import filtered_documents, search_documents

JUDGMENTS_FILE = Path(__file__).resolve().parent / 'seed' / 'search_judgments.json'
CUTOFF = 10


def keyword_search(query, filters):
    """Phase 1's search, kept unchanged as the baseline to beat."""
    documents = filtered_documents(filters)
    if query:
        documents = documents.filter(
            Q(title__icontains=query) | Q(content_text__icontains=query)
        )
    return documents.order_by('-published_at', '-id')


ENGINES = {'Phase 1 keyword': keyword_search, 'Phase 2 BM25': search_documents}


def ndcg(ranked, grades, k=CUTOFF):
    """Normalised discounted cumulative gain: 1.0 means the best possible order."""
    def dcg(gains):
        return sum((2 ** gain - 1) / math.log2(rank + 2) for rank, gain in enumerate(gains))

    ideal = dcg(sorted(grades.values(), reverse=True)[:k])
    return dcg([grades.get(slug, 0) for slug in ranked[:k]]) / ideal if ideal else 0.0


def reciprocal_rank(ranked, grades):
    """1 / the rank of the first result graded 2 or more. 0 if there is none."""
    for rank, slug in enumerate(ranked, start=1):
        if grades.get(slug, 0) >= 2:
            return 1 / rank
    return 0.0


def recall(ranked, grades, k=CUTOFF):
    """Share of the judged articles that appear in the top k."""
    return len(set(ranked[:k]) & set(grades)) / len(grades) if grades else 0.0


def evaluate(engine, judgments=None):
    """Score one engine. Returns (per-query rows, averages)."""
    if judgments is None:
        judgments = json.loads(JUDGMENTS_FILE.read_text(encoding='utf-8'))
    rows = []
    for judged in judgments:
        ranked = [document.slug for document in engine(judged['query'], {})]
        grades = judged['relevant']
        rows.append({
            'query': judged['query'],
            'results': len(ranked),
            'ndcg': ndcg(ranked, grades),
            'mrr': reciprocal_rank(ranked, grades),
            'recall': recall(ranked, grades),
        })
    averages = {
        metric: sum(row[metric] for row in rows) / len(rows) if rows else 0.0
        for metric in ('ndcg', 'mrr', 'recall')
    }
    return rows, averages
