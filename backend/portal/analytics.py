from django.contrib import admin
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Count, Sum
from django.db.models.functions import Lower
from django.shortcuts import render
from django.urls import reverse_lazy

from .models import Document, SearchClickLog

TOP_COUNT = 10


def top_queries(searches):
    """Count searches by their words, so Budget and budget are one query."""
    return (
        searches.annotate(query=Lower('query_string'))
        .values('query')
        .annotate(total=Count('id'))
        .order_by('-total', 'query')[:TOP_COUNT]
    )


def get_analytics():
    # Search rows have no position. A click keeps its position even if the
    # document is later deleted. Filter-only searches have no words to rank.
    searches = SearchClickLog.objects.filter(position__isnull=True).exclude(query_string='')
    return {
        'total_views': Document.objects.aggregate(total=Sum('views_count'))['total'] or 0,
        'most_viewed': Document.objects.filter(views_count__gt=0).order_by(
            '-views_count', 'title'
        )[:TOP_COUNT],
        'top_queries': top_queries(searches),
        'zero_result_queries': top_queries(searches.filter(result_count=0)),
        'most_clicked': Document.objects.annotate(clicks=Count('search_clicks'))
        .filter(clicks__gt=0)
        .order_by('-clicks', 'title')[:TOP_COUNT],
    }


# Guests go to the login page. Logged-in users without the permission get a 403.
@login_required(login_url=reverse_lazy('admin:login'))
@permission_required('portal.view_analytics', raise_exception=True)
def analytics_dashboard(request):
    context = {**admin.site.each_context(request), 'title': 'Analytics', **get_analytics()}
    return render(request, 'portal/analytics.html', context)
