"""Tests for Phase 2: the analyzer, the inverted index, BM25 ranking and evaluation."""
import datetime
import io
import tempfile

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from .evaluation import evaluate, keyword_search, ndcg, recall, reciprocal_rank
from .models import Category, Document, IndexedDocument, Posting, Tag, User
from .search import search_documents
from .text import analyze, fold, parse_query, stem


def on(day):
    return datetime.datetime(2026, 3, day, 12, tzinfo=datetime.timezone.utc)


class TextTests(SimpleTestCase):
    def test_fold_lowercases_and_drops_accents(self):
        self.assertEqual(fold('Café NAÏVE'), 'cafe naive')

    def test_stem_undoes_plurals_only(self):
        cases = {
            'harbours': 'harbour', 'policies': 'policy', 'boxes': 'boxe', 'bus': 'bus',
            'glass': 'glass', 'is': 'is', 'running': 'running', "farmer's": 'farmer',
        }
        for word, expected in cases.items():
            with self.subTest(word=word):
                self.assertEqual(stem(word), expected)

    def test_analyze_splits_on_punctuation_and_keeps_order(self):
        self.assertEqual(
            analyze('The harbour’s Cafés: HARBOURS, 2026 & Lake_Verrin'),
            ['the', 'harbour', 'cafe', 'harbour', '2026', 'lake', 'verrin'],
        )

    def test_apostrophes_inside_words_are_kept(self):
        self.assertEqual(analyze("don't o'clock"), ["don't", "o'clock"])

    def test_parse_query_finds_terms_and_phrases(self):
        terms, phrases = parse_query('solar "Wind Turbines" “heat pumps” solar')
        self.assertEqual(terms, ['solar', 'wind', 'turbine', 'heat', 'pump'])
        self.assertEqual(phrases, [['wind', 'turbine'], ['heat', 'pump']])

    def test_one_word_in_quotes_is_just_a_term(self):
        self.assertEqual(parse_query('"solar"'), (['solar'], []))

    def test_symbols_only_give_nothing(self):
        self.assertEqual(parse_query('% "" !!'), ([], []))


class EngineTestCase(TestCase):
    def setUp(self):
        self.author = User.objects.create_user('author')
        self.category = Category.objects.create(name='News', slug='news')
        self.count = 0

    def make(self, title, body='Plain text.', status=Document.Status.PUBLISHED, **fields):
        self.count += 1
        fields.setdefault('category', self.category)
        return Document.objects.create(
            title=title, slug=f'doc-{self.count}', content=f'<p>{body}</p>',
            author=self.author, status=status, **fields,
        )

    def found(self, query, **filters):
        return [document.title for document in search_documents(query, filters)]


class IndexUpkeepTests(EngineTestCase):
    def terms(self, document):
        return set(Posting.objects.filter(document=document).values_list('term', flat=True))

    def test_published_document_is_indexed_with_lengths(self):
        document = self.make('Solar farm', body='Sheep graze under the panels.', summary='Short')
        entry = IndexedDocument.objects.get(document=document)
        # Body is the summary then the content: Short sheep graze under the panels.
        self.assertEqual((entry.title_length, entry.body_length), (2, 6))
        self.assertTrue({'solar', 'farm', 'sheep', 'panel', 'short'} <= self.terms(document))

    def test_positions_and_counts_are_stored(self):
        document = self.make('Title', body='red blue red')
        posting = Posting.objects.get(document=document, field='body', term='red')
        self.assertEqual((posting.tf, posting.positions), (2, [0, 2]))  # the summary is empty

    def test_drafts_are_not_indexed(self):
        document = self.make('Secret plan', status=Document.Status.DRAFT)
        self.assertFalse(IndexedDocument.objects.filter(document=document).exists())
        self.assertFalse(Posting.objects.filter(document=document).exists())

    def test_publishing_and_unpublishing_take_effect_at_once(self):
        document = self.make('Budget news', status=Document.Status.DRAFT)
        self.assertEqual(self.found('budget'), [])
        document.status = Document.Status.PUBLISHED
        document.save()
        self.assertEqual(self.found('budget'), ['Budget news'])
        document.status = Document.Status.UNPUBLISHED
        document.save()
        self.assertEqual(self.found('budget'), [])
        self.assertFalse(Posting.objects.filter(document=document).exists())

    def test_editing_replaces_the_old_terms(self):
        document = self.make('Budget news')
        document.title = 'Harbour news'
        document.save()
        self.assertEqual(self.found('budget'), [])
        self.assertEqual(self.found('harbour'), ['Harbour news'])
        self.assertEqual(IndexedDocument.objects.filter(document=document).count(), 1)

    def test_deleting_removes_postings(self):
        document = self.make('Budget news')
        document.delete()
        self.assertFalse(Posting.objects.exists())
        self.assertFalse(IndexedDocument.objects.exists())

    def test_counting_a_view_does_not_reindex(self):
        document = self.make('Budget news')
        before = list(Posting.objects.filter(document=document).values_list('pk', flat=True))
        self.client.get(f'/api/documents/{document.slug}')
        after = list(Posting.objects.filter(document=document).values_list('pk', flat=True))
        self.assertEqual(before, after)

    def test_build_index_rebuilds_from_scratch(self):
        self.make('Budget news')
        self.make('Hidden draft', status=Document.Status.DRAFT)
        Posting.objects.all().delete()
        IndexedDocument.objects.all().delete()
        output = io.StringIO()
        call_command('build_index', stdout=output)
        self.assertIn('Indexed 1 documents', output.getvalue())
        self.assertEqual(self.found('budget'), ['Budget news'])


class RankingTests(EngineTestCase):
    def test_one_title_match_beats_two_body_matches(self):
        # With equal field weights the body's two mentions would win.
        self.make('Harbour report', body='Something else entirely.')
        self.make('Weather report', body='Harbour harbour.')
        self.assertEqual(self.found('harbour'), ['Harbour report', 'Weather report'])

    def test_rare_word_counts_more_than_a_common_one(self):
        # The two matches mirror each other, so only IDF can separate them.
        # "council" is in every document; "otter" is in two. Repeating the
        # rare word should therefore win. Without IDF they would tie, and the
        # newer one ("Mostly council") would come first.
        self.make('Survey', body='otter otter otter council')
        self.make('Mostly council', body='otter council council council')
        for number in range(5):
            self.make(f'Meeting {number}', body='council')
        self.assertEqual(self.found('otter council'), ['Survey', 'Mostly council'])

    def test_repeating_a_word_helps_but_with_diminishing_returns(self):
        self.make('One', body='solar ' + 'filler ' * 20)
        self.make('Three', body='solar solar solar ' + 'filler ' * 18)
        self.assertEqual(self.found('solar'), ['Three', 'One'])

    def test_short_fields_beat_long_ones_for_the_same_count(self):
        self.make('Short', body='solar panels')
        self.make('Long', body='solar ' + 'filler ' * 60)
        self.assertEqual(self.found('solar'), ['Short', 'Long'])

    def test_every_word_must_appear(self):
        self.make('Solar farm')
        self.make('Wind farm')
        self.assertEqual(self.found('solar farm'), ['Solar farm'])

    def test_plurals_and_accents_match(self):
        self.make('Harbours of the coast', body='A café by the water.')
        self.assertEqual(self.found('harbour'), ['Harbours of the coast'])
        self.assertEqual(self.found('CAFE'), ['Harbours of the coast'])

    def test_phrase_needs_words_side_by_side_in_one_field(self):
        self.make('Heat pumps arrive', body='Plain text.')
        self.make('Pumps and heat', body='Plain text.')
        self.make('Heat', body='Pumps are mentioned in the body.')
        self.assertEqual(self.found('"heat pumps"'), ['Heat pumps arrive'])
        self.assertEqual(len(self.found('heat pumps')), 3)

    def test_ties_go_to_the_newer_article(self):
        self.make('Budget news', published_at=on(1))
        self.make('Budget news', published_at=on(9))
        dates = [d.published_at.day for d in search_documents('budget', {})]
        self.assertEqual(dates, [9, 1])

    def test_filters_still_apply(self):
        sport = Category.objects.create(name='Sport', slug='sport')
        tag = Tag.objects.create(name='Tech', slug='tech')
        self.make('Budget news', published_at=on(1))
        self.make('Budget sport', category=sport, published_at=on(5)).tags.add(tag)
        self.assertEqual(self.found('budget', category='sport'), ['Budget sport'])
        self.assertEqual(self.found('budget', tag='tech'), ['Budget sport'])
        self.assertEqual(self.found('budget', to=datetime.date(2026, 3, 2)), ['Budget news'])

    def test_document_hidden_without_a_save_never_appears(self):
        # QuerySet.update() skips the index upkeep, so the search must still check status.
        document = self.make('Budget news')
        Document.objects.filter(pk=document.pk).update(status=Document.Status.DRAFT)
        self.assertEqual(self.found('budget'), [])

    def test_unknown_words_and_symbols_find_nothing(self):
        self.make('Budget news')
        self.assertEqual(self.found('zebra'), [])
        self.assertEqual(self.found('%'), [])

    def test_empty_query_lists_filtered_documents_newest_first(self):
        self.make('Old', published_at=on(1))
        self.make('New', published_at=on(9))
        self.assertEqual(self.found(''), ['New', 'Old'])


class MetricTests(SimpleTestCase):
    grades = {'a': 3, 'b': 1}

    def test_ndcg_is_one_for_the_ideal_order(self):
        self.assertAlmostEqual(ndcg(['a', 'b', 'x'], self.grades), 1.0)

    def test_ndcg_drops_when_the_best_result_is_late(self):
        self.assertLess(ndcg(['x', 'b', 'a'], self.grades), ndcg(['a', 'b'], self.grades))
        self.assertEqual(ndcg(['x', 'y'], self.grades), 0.0)

    def test_ndcg_only_counts_the_top_ten(self):
        self.assertEqual(ndcg(['x'] * 10 + ['a'], self.grades), 0.0)

    def test_reciprocal_rank_needs_a_grade_of_two(self):
        self.assertEqual(reciprocal_rank(['b', 'x', 'a'], self.grades), 1 / 3)
        self.assertEqual(reciprocal_rank(['b'], self.grades), 0.0)

    def test_recall(self):
        self.assertEqual(recall(['a', 'x'], self.grades), 0.5)


class EvaluationTests(EngineTestCase):
    def test_evaluate_scores_an_engine_per_query(self):
        self.make('Solar farm opens')
        judgments = [
            {'query': 'solar', 'relevant': {'doc-1': 3}},
            {'query': 'wind', 'relevant': {'doc-1': 1}},
        ]
        rows, averages = evaluate(search_documents, judgments)
        self.assertEqual([row['ndcg'] for row in rows], [1.0, 0.0])
        self.assertEqual(averages['ndcg'], 0.5)

    def test_baseline_is_the_phase_1_substring_search(self):
        self.make('Recycling centre')
        self.assertEqual([d.title for d in keyword_search('cycling', {})], ['Recycling centre'])
        self.assertEqual(self.found('cycling'), [])


class SeededCorpusTests(TestCase):
    """The real 100 articles and the judged queries in seed/search_judgments.json."""

    def setUp(self):
        media = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(media.cleanup)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        call_command('seed_data', stdout=io.StringIO())

    def test_seeding_indexes_every_published_article(self):
        published = Document.objects.filter(status=Document.Status.PUBLISHED).count()
        self.assertEqual(IndexedDocument.objects.count(), published)

    def test_bm25_beats_the_phase_1_baseline(self):
        _, baseline = evaluate(keyword_search)
        _, bm25 = evaluate(search_documents)
        for metric in ('ndcg', 'mrr', 'recall'):
            with self.subTest(metric=metric):
                self.assertGreater(bm25[metric], baseline[metric])
