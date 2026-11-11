from django.core.management.base import BaseCommand

from portal.indexing import rebuild_index
from portal.models import Posting


class Command(BaseCommand):
    help = 'Rebuild the search index from every published document.'

    def handle(self, *args, **options):
        count = rebuild_index()
        self.stdout.write(self.style.SUCCESS(
            f'Indexed {count} documents ({Posting.objects.count()} postings).'
        ))
