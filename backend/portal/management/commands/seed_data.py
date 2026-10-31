"""Fill the database with demo data. Safe to run again: nothing is duplicated."""
import datetime
import html
import io
import json
import random
import textwrap
import uuid
from pathlib import Path

from django.contrib.auth.models import Group
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageDraw, ImageFont

from portal.models import (
    Category,
    Comment,
    Document,
    Like,
    Report,
    SearchClickLog,
    SiteSetting,
    Tag,
    User,
    UserTag,
)
from portal.roles import CONTENT_MANAGER, DATA_SEO, MODERATOR, SUPER_ADMIN
from portal.search import search_documents

ARTICLES_FILE = Path(__file__).resolve().parents[2] / 'seed' / 'articles.json'

# Demo only, and listed in the README. Never reuse this anywhere real.
DEMO_PASSWORD = 'demo-password-123'

ACCOUNTS = [
    ('superadmin', 'Sam Superadmin', SUPER_ADMIN),
    ('editor', 'Erin Editor', CONTENT_MANAGER),
    ('moderator', 'Max Moderator', MODERATOR),
    ('seo', 'Dana Seo', DATA_SEO),
    ('reader1', 'Riley Reader', None),
    ('reader2', 'Robin Reader', None),
]

CATEGORY_COLOURS = {
    'Technology': (31, 78, 121),
    'Business': (122, 75, 22),
    'Health': (21, 112, 96),
    'Environment': (58, 110, 40),
    'Culture': (120, 40, 104),
    'Sports': (163, 38, 27),
}

COMMENTS = [
    'This is great news for the town. Thanks for covering it.',
    'I had no idea this was happening so close to home.',
    'My neighbour was involved in this and says it has been a huge effort.',
    'Who is paying for all of this? I would like to see the figures.',
    'We need more stories like this one.',
    'Interesting, but I wonder how it will work over the winter.',
    'Well done to everyone who made this happen.',
    'I tried this last month and was very impressed.',
    'Is there a way for residents to get involved?',
    'The council should have done this years ago.',
    'A balanced report. I appreciated hearing from both sides.',
    'My daughter would love this. Sharing it with her now.',
    'I am not convinced this will last, but I hope I am wrong.',
    'Good to see young people leading the way.',
    'Does anyone know whether this will reach the eastern side of town?',
]

SPAM_COMMENTS = [
    'WIN A FREE PHONE!!! Click the link in my profile right now!!!',
    'Make thousands from home every week, ask me how.',
    'Cheap watches, best prices, message me today.',
    'You are all fools if you believe any of this rubbish.',
    'Buy followers cheap, fast delivery guaranteed.',
]

# (query as typed, how many searches). Mixed case on purpose: the
# dashboard groups these together. The last few find nothing.
SEARCHES = [
    ('harbour', 9), ('Harbour', 3), ('solar', 7), ('school', 6), ('hospital', 6),
    ('football', 5), ('river', 5), ('library', 4), ('energy', 4), ('Bakery', 3),
    ('salmon', 3), ('marathon', 2), ('time machine', 3), ('moon base', 2),
    ('dragon sightings', 1),
]


def make_banner(title, category):
    """Draw a simple banner, so no outside images are needed."""
    size = (1200, 630)
    colour = CATEGORY_COLOURS[category]
    dark = tuple(value // 3 for value in colour)
    gradient = Image.linear_gradient('L').resize(size)
    image = Image.composite(Image.new('RGB', size, dark), Image.new('RGB', size, colour), gradient)

    draw = ImageDraw.Draw(image)
    draw.text((60, 60), category.upper(), fill='white', font=ImageFont.load_default(size=34))
    lines = textwrap.wrap(title, width=30)[:4]
    draw.multiline_text(
        (60, 170), '\n'.join(lines), fill='white', spacing=18,
        font=ImageFont.load_default(size=64),
    )

    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=80)
    return ContentFile(buffer.getvalue())


class Command(BaseCommand):
    help = 'Load the demo articles, accounts, comments, likes, reports and search logs.'

    def handle(self, *args, **options):
        users = self.create_accounts()
        articles = json.loads(ARTICLES_FILE.read_text(encoding='utf-8'))
        documents = self.create_documents(articles, users)
        published = [d for d in documents if d.status == Document.Status.PUBLISHED]
        comments = self.create_comments(published, users)
        self.create_likes_and_tags(published, users)
        self.create_reports(comments, users)
        self.create_search_logs(users)
        self.create_settings()
        self.stdout.write(self.style.SUCCESS(
            f'{Document.objects.count()} documents, {User.objects.count()} users, '
            f'{Comment.objects.count()} comments, {Like.objects.count()} likes, '
            f'{Report.objects.count()} reports, {SearchClickLog.objects.count()} search log rows.'
        ))

    def create_accounts(self):
        users = {}
        for username, display_name, role in ACCOUNTS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'display_name': display_name, 'email': f'{username}@example.com'},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            if role:
                user.groups.add(Group.objects.get(name=role))
            users[username] = user
        return users

    def create_documents(self, articles, users):
        # A fixed seed gives the same choices each run, so reruns change nothing.
        rng = random.Random(42)
        days_ago = list(range(1, len(articles) + 1))
        rng.shuffle(days_ago)
        now = timezone.now()
        documents = []
        for index, article in enumerate(articles):
            status = Document.Status.PUBLISHED
            if index % 25 == 24:
                status = Document.Status.DRAFT
            elif index % 50 == 10:
                status = Document.Status.UNPUBLISHED
            published_at = None
            if status != Document.Status.DRAFT:
                published_at = now - datetime.timedelta(days=days_ago[index])
            views = rng.randint(10, 900) if status == Document.Status.PUBLISHED else 0
            documents.append(self.create_document(article, users, status, published_at, views))
        return documents

    def create_document(self, article, users, status, published_at, views):
        title = article['title']
        category, _ = Category.objects.get_or_create(
            name=article['category'], defaults={'slug': slugify(article['category'])}
        )
        paragraphs = (html.escape(text, quote=False) for text in article['paragraphs'])
        document, created = Document.objects.get_or_create(
            slug=slugify(title),
            defaults={
                'title': title,
                'content': ''.join(f'<p>{text}</p>' for text in paragraphs),
                'summary': article['summary'],
                'category': category,
                'author': users['editor'],
                'image_alt': f'Banner reading "{title}"',
                'status': status,
                'published_at': published_at,
                'views_count': views,
                'seo_title': title[:255],
                'seo_description': article['summary'],
                'seo_keywords': ', '.join(article['tags']),
            },
        )
        if created:
            tags = [
                Tag.objects.get_or_create(name=name, defaults={'slug': slugify(name)})[0]
                for name in article['tags']
            ]
            document.tags.set(tags)
        # Uploads are not in Git, so a fresh clone needs its banners drawn again.
        if not document.image or not document.image.storage.exists(document.image.name):
            document.image.save(
                f'{document.slug[:80]}.jpg', make_banner(title, article['category'])
            )
        return document

    def create_comments(self, documents, users):
        rng = random.Random(43)
        people = list(users.values())
        comments = []
        for document in documents[::2]:
            for _ in range(rng.randint(1, 4)):
                comments.append(Comment.objects.get_or_create(
                    document=document, user=rng.choice(people), body=rng.choice(COMMENTS),
                )[0])
        # Spam for the moderation screens. The last two are already hidden.
        for index, body in enumerate(SPAM_COMMENTS):
            status = Comment.Status.HIDDEN if index >= 3 else Comment.Status.VISIBLE
            comments.append(Comment.objects.get_or_create(
                document=documents[index], user=users['reader2'], body=body,
                defaults={'status': status},
            )[0])
        return comments

    def create_likes_and_tags(self, documents, users):
        rng = random.Random(44)
        people = list(users.values())
        tags = list(Tag.objects.order_by('slug'))
        for document in documents:
            for user in rng.sample(people, rng.randint(0, 5)):
                Like.objects.get_or_create(user=user, document=document)
        for document in documents[:30]:
            UserTag.objects.get_or_create(
                user=rng.choice(people), document=document, tag=rng.choice(tags)
            )

    def create_reports(self, comments, users):
        spam = comments[-len(SPAM_COMMENTS):]
        for index, comment in enumerate(spam):
            # The first three wait for a moderator. The hidden ones are done.
            done = index >= 3
            Report.objects.get_or_create(
                comment=comment,
                reporter=users['reader1'],
                reason='This looks like spam.',
                defaults={
                    'status': Report.Status.RESOLVED if done else Report.Status.OPEN,
                    'resolved_by': users['moderator'] if done else None,
                },
            )

    def create_search_logs(self, users):
        rng = random.Random(45)
        readers = [None, None, users['reader1'], users['reader2']]
        namespace = uuid.UUID('6f1d3a52-0000-4000-8000-000000000000')
        number = 0
        for query, repeats in SEARCHES:
            results = list(search_documents(query, {}).values_list('pk', flat=True))
            for _ in range(repeats):
                number += 1
                # Same number, same id: that is how a rerun spots an existing row.
                query_id = uuid.uuid5(namespace, f'search-{number}')
                user = rng.choice(readers)
                clicks = rng.random() < 0.7
                position = rng.randint(1, min(len(results), 10)) if results else None
                if SearchClickLog.objects.filter(query_id=query_id).exists():
                    continue
                SearchClickLog.objects.create(
                    user=user, query_string=query, query_id=query_id,
                    result_count=len(results),
                )
                if clicks and results:
                    SearchClickLog.objects.create(
                        user=user, query_string=query, query_id=query_id,
                        result_count=len(results), position=position,
                        clicked_doc_id=results[position - 1],
                    )

    def create_settings(self):
        defaults = {'site_name': 'News Portal', 'tagline': 'Local news, told plainly.'}
        for key, value in defaults.items():
            SiteSetting.objects.get_or_create(key=key, defaults={'value': value})
