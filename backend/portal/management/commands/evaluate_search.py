from django.core.management.base import BaseCommand

from portal.evaluation import CUTOFF, ENGINES, evaluate


class Command(BaseCommand):
    help = 'Compare the Phase 1 and Phase 2 search engines on the judged test queries.'

    def add_arguments(self, parser):
        parser.add_argument('--details', action='store_true', help='Show every query.')

    def handle(self, *args, **options):
        results = {name: evaluate(engine) for name, engine in ENGINES.items()}

        if options['details']:
            names = list(results)
            self.stdout.write(f"{'Query':34} " + '  '.join(f'{n:>20}' for n in names))
            per_engine = [results[name][0] for name in names]
            for rows in zip(*per_engine):
                cells = [f"nDCG {row['ndcg']:.2f} ({row['results']:>3})" for row in rows]
                self.stdout.write(f"{rows[0]['query'][:34]:34} " + '  '.join(f'{c:>20}' for c in cells))
            self.stdout.write('(the number in brackets is how many results the engine returned)\n')

        self.stdout.write(f"{'Engine':18} {f'nDCG@{CUTOFF}':>9} {'MRR':>7} {f'Recall@{CUTOFF}':>10}")
        for name, (rows, averages) in results.items():
            self.stdout.write(
                f"{name:18} {averages['ndcg']:>9.3f} {averages['mrr']:>7.3f} {averages['recall']:>10.3f}"
            )
        self.stdout.write(f'Averaged over {len(rows)} judged queries.')
