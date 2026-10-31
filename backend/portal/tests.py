import collections
import datetime
import io
import json
import tempfile
import uuid

from django.contrib.admin.models import LogEntry
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient, APITestCase

from .models import (
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
from .management.commands.seed_data import ACCOUNTS, ARTICLES_FILE, DEMO_PASSWORD
from .roles import CONTENT_MANAGER, DATA_SEO, MODERATOR, STAFF_ROLES, SUPER_ADMIN
from .search import search_documents


def crud(model):
    return [f'portal.{action}_{model}' for action in ('add', 'change', 'delete')]


# Each action from the CLAUDE.md role table, as the permissions it needs.
# "Comment, like, tag, report" needs no permission, only a login, so the
# API tests in Step 5 cover it.
ACTIONS = {
    'manage users': crud('user'),
    'manage roles': ['auth.add_group', 'auth.change_group', 'auth.delete_group'],
    'manage settings': crud('sitesetting'),
    'view system logs': ['admin.view_logentry'],
    'edit documents': crud('document'),
    'publish': ['portal.publish_document'],
    'manage taxonomy': crud('category') + crud('tag'),
    'moderate': ['portal.change_comment', 'portal.change_report'],
    'edit seo': ['portal.edit_seo'],
    'view analytics': ['portal.view_analytics'],
}

ALLOWED = {
    SUPER_ADMIN: set(ACTIONS),
    CONTENT_MANAGER: {'edit documents', 'publish', 'manage taxonomy', 'edit seo'},
    MODERATOR: {'moderate'},
    DATA_SEO: {'edit seo', 'view analytics'},
}


def make_user(role=None, username='someone'):
    user = User.objects.create_user(username)
    if role:
        user.groups.add(Group.objects.get(name=role))
    # Fetch again so is_staff and the permission cache are fresh.
    return User.objects.get(pk=user.pk)


class RolePermissionTests(TestCase):
    def assert_role_matches_table(self, role):
        user = make_user(role)
        for action, permissions in ACTIONS.items():
            allowed = action in ALLOWED[role]
            for permission in permissions:
                with self.subTest(role=role, action=action, permission=permission):
                    self.assertEqual(user.has_perm(permission), allowed)

    def test_super_admin(self):
        self.assert_role_matches_table(SUPER_ADMIN)

    def test_content_manager(self):
        self.assert_role_matches_table(CONTENT_MANAGER)

    def test_moderator(self):
        self.assert_role_matches_table(MODERATOR)

    def test_data_seo(self):
        self.assert_role_matches_table(DATA_SEO)

    def test_reader_has_no_permissions(self):
        user = make_user()
        self.assertEqual(user.get_all_permissions(), set())

    def test_super_admin_group_has_every_permission(self):
        group = Group.objects.get(name=SUPER_ADMIN)
        self.assertEqual(group.permissions.count(), Permission.objects.count())


class StaffAccessTests(TestCase):
    def test_every_staff_role_gets_is_staff(self):
        for role in STAFF_ROLES:
            with self.subTest(role=role):
                user = make_user(role)
                self.assertTrue(user.is_staff)
                user.delete()

    def test_reader_is_not_staff(self):
        self.assertFalse(make_user().is_staff)

    def test_leaving_a_role_removes_is_staff(self):
        user = make_user(MODERATOR)
        user.groups.clear()
        user.refresh_from_db()
        self.assertFalse(user.is_staff)

    def test_keeping_one_role_keeps_is_staff(self):
        user = make_user(MODERATOR)
        user.groups.add(Group.objects.get(name=DATA_SEO))
        user.groups.remove(Group.objects.get(name=MODERATOR))
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_adding_from_the_group_side_sets_is_staff(self):
        user = make_user()
        Group.objects.get(name=DATA_SEO).user_set.add(user)
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_superuser_stays_staff_without_a_role(self):
        user = User.objects.create_superuser('root')
        user.groups.add(Group.objects.get(name=MODERATOR))
        user.groups.clear()
        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_staff_can_open_admin_and_reader_cannot(self):
        self.client.force_login(make_user(MODERATOR))
        self.assertEqual(self.client.get('/admin/').status_code, 200)
        self.client.logout()
        User.objects.all().delete()
        self.client.force_login(make_user())
        self.assertEqual(self.client.get('/admin/').status_code, 302)


def make_document(author, **fields):
    category, _ = Category.objects.get_or_create(name='News', slug='news')
    fields.setdefault('title', 'A title')
    fields.setdefault('slug', 'a-title')
    fields.setdefault('content', '<p>Body</p>')
    return Document.objects.create(category=category, author=author, **fields)


class DocumentSaveTests(TestCase):
    def setUp(self):
        self.author = make_user()

    def test_scripts_and_event_handlers_are_removed(self):
        document = make_document(self.author)
        document.content = '<p onclick="steal()">Hi</p><script>alert(1)</script>'
        document.save()
        document.refresh_from_db()
        self.assertEqual(document.content, '<p>Hi</p>')
        self.assertNotIn('alert', document.content_text)

    def test_safe_html_is_kept(self):
        document = make_document(self.author)
        document.content = '<h2>Head</h2><p><strong>Bold</strong> text</p>'
        document.save()
        self.assertEqual(document.content, '<h2>Head</h2><p><strong>Bold</strong> text</p>')

    def test_content_text_is_clean(self):
        document = make_document(self.author)
        document.content = '<p>Fish &amp;  chips&nbsp;today</p>\n\n<ul><li>one</li><li>two</li></ul>'
        document.save()
        self.assertEqual(document.content_text, 'Fish & chips today one two')

    def test_inline_tags_do_not_split_words(self):
        document = make_document(self.author)
        document.content = '<p>un<em>believ</em>able, <a href="https://example.com">link</a>.</p>'
        document.save()
        self.assertEqual(document.content_text, 'unbelievable, link.')

    def test_escaped_html_stays_as_text(self):
        document = make_document(self.author)
        document.content = '<p>Use &lt;b&gt; for bold</p>'
        document.save()
        self.assertEqual(document.content_text, 'Use <b> for bold')
        self.assertIn('&lt;b&gt;', document.content)

    def test_published_at_is_set_the_first_time_only(self):
        document = make_document(self.author)
        self.assertIsNone(document.published_at)
        document.status = Document.Status.PUBLISHED
        document.save()
        first = document.published_at
        self.assertIsNotNone(first)
        document.status = Document.Status.UNPUBLISHED
        document.save()
        document.status = Document.Status.PUBLISHED
        document.save()
        self.assertEqual(document.published_at, first)


class AdminTestCase(TestCase):
    def login(self, role=None):
        user = make_user(role, username='logged-in')
        self.client.force_login(user)
        return user

    def run_action(self, model, action, objects):
        return self.client.post(
            reverse(f'admin:portal_{model}_changelist'),
            {'action': action, '_selected_action': [obj.pk for obj in objects]},
            follow=True,
        )

    def form_for(self, url):
        return self.client.get(url).context['adminform'].form


class ContentManagerAdminTests(AdminTestCase):
    def setUp(self):
        self.user = self.login(CONTENT_MANAGER)
        self.category = Category.objects.create(name='News', slug='news')

    def add_document(self, **extra):
        return self.client.post(reverse('admin:portal_document_add'), {
            'title': 'Created in admin',
            'slug': 'created-in-admin',
            'summary': 'Short',
            'content': '<p>Hello <b>world</b></p><script>alert(1)</script>',
            'category': self.category.pk,
            'status': Document.Status.DRAFT,
            **extra,
        })

    def test_create_then_publish(self):
        response = self.add_document()
        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(slug='created-in-admin')
        self.assertEqual(document.author, self.user)
        self.assertEqual(document.content_text, 'Hello world')
        self.assertIsNone(document.published_at)

        self.run_action('document', 'publish', [document])
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.PUBLISHED)
        self.assertIsNotNone(document.published_at)

    def test_author_cannot_be_chosen(self):
        other = make_user(username='other')
        self.add_document(author=other.pk)
        self.assertEqual(Document.objects.get().author, self.user)

    def test_unpublish_keeps_published_at(self):
        document = make_document(self.user, status=Document.Status.PUBLISHED)
        first = document.published_at
        self.run_action('document', 'unpublish', [document])
        document.refresh_from_db()
        self.assertEqual(document.status, Document.Status.UNPUBLISHED)
        self.assertEqual(document.published_at, first)

    def test_publish_action_is_logged(self):
        document = make_document(self.user)
        self.run_action('document', 'publish', [document])
        self.assertTrue(LogEntry.objects.filter(change_message='Published').exists())

    def test_upload_image(self):
        buffer = io.BytesIO()
        Image.new('RGB', (2, 2)).save(buffer, 'PNG')
        upload = SimpleUploadedFile('photo.png', buffer.getvalue(), 'image/png')
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as media:
            with self.settings(MEDIA_ROOT=media):
                self.add_document(image=upload, image_alt='A photo')
        document = Document.objects.get()
        self.assertTrue(document.image.name.startswith('documents/'))

    def test_can_manage_taxonomy_but_not_users_or_settings(self):
        self.assertEqual(self.client.get(reverse('admin:portal_tag_add')).status_code, 200)
        self.assertEqual(self.client.get(reverse('admin:portal_user_changelist')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:portal_sitesetting_changelist')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:admin_logentry_changelist')).status_code, 403)


class DataSeoAdminTests(AdminTestCase):
    def setUp(self):
        self.user = self.login(DATA_SEO)
        self.document = make_document(make_user(username='author'))
        self.url = reverse('admin:portal_document_change', args=[self.document.pk])

    def test_form_offers_only_seo_fields(self):
        self.assertEqual(set(self.form_for(self.url).fields), {
            'seo_title', 'seo_description', 'seo_keywords', 'image_alt',
        })

    def test_can_save_seo_but_nothing_else(self):
        response = self.client.post(self.url, {
            'seo_title': 'Better title',
            'seo_description': 'Description',
            'seo_keywords': 'a, b',
            'image_alt': 'Alt text',
            'title': 'Hijacked',
            'content': '<p>Hijacked</p>',
            'status': Document.Status.PUBLISHED,
        })
        self.assertEqual(response.status_code, 302)
        self.document.refresh_from_db()
        self.assertEqual(self.document.seo_title, 'Better title')
        self.assertEqual(self.document.image_alt, 'Alt text')
        self.assertEqual(self.document.title, 'A title')
        self.assertEqual(self.document.content, '<p>Body</p>')
        self.assertEqual(self.document.status, Document.Status.DRAFT)

    def test_cannot_add_or_delete(self):
        self.assertEqual(self.client.get(reverse('admin:portal_document_add')).status_code, 403)
        delete_url = reverse('admin:portal_document_delete', args=[self.document.pk])
        self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)
        self.assertTrue(Document.objects.filter(pk=self.document.pk).exists())

    def test_cannot_publish(self):
        response = self.client.get(reverse('admin:portal_document_changelist'))
        self.assertIsNone(response.context['action_form'])
        self.run_action('document', 'publish', [self.document])
        self.document.refresh_from_db()
        self.assertEqual(self.document.status, Document.Status.DRAFT)


class ModeratorAdminTests(AdminTestCase):
    def setUp(self):
        self.user = self.login(MODERATOR)
        self.reader = make_user(username='reader')
        document = make_document(self.reader)
        self.comment = Comment.objects.create(document=document, user=self.reader, body='Spam')
        self.report = Report.objects.create(comment=self.comment, reporter=self.reader, reason='Spam')

    def test_hide_comment(self):
        self.run_action('comment', 'hide', [self.comment])
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.status, Comment.Status.HIDDEN)

    def test_cannot_rewrite_a_comment(self):
        url = reverse('admin:portal_comment_change', args=[self.comment.pk])
        self.client.post(url, {'body': 'Rewritten', 'status': Comment.Status.VISIBLE})
        self.comment.refresh_from_db()
        self.assertEqual(self.comment.body, 'Spam')

    def test_resolve_report_records_who(self):
        self.run_action('report', 'resolve', [self.report])
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, Report.Status.RESOLVED)
        self.assertEqual(self.report.resolved_by, self.user)

    def test_resolving_twice_keeps_the_first_resolver(self):
        first = make_user(username='first')
        Report.objects.filter(pk=self.report.pk).update(
            status=Report.Status.RESOLVED, resolved_by=first
        )
        self.run_action('report', 'resolve', [self.report])
        self.report.refresh_from_db()
        self.assertEqual(self.report.resolved_by, first)

    def test_cannot_reach_documents(self):
        self.assertEqual(self.client.get(reverse('admin:portal_document_changelist')).status_code, 403)


class SuperAdminTests(AdminTestCase):
    def setUp(self):
        self.user = self.login(SUPER_ADMIN)

    def test_every_screen_opens(self):
        for name in ('portal_user', 'portal_category', 'portal_tag', 'portal_document',
                     'portal_comment', 'portal_report', 'portal_sitesetting',
                     'admin_logentry', 'auth_group'):
            with self.subTest(screen=name):
                response = self.client.get(reverse(f'admin:{name}_changelist'))
                self.assertEqual(response.status_code, 200)

    def test_can_author_for_someone_else(self):
        other = make_user(username='other')
        category = Category.objects.create(name='News', slug='news')
        self.client.post(reverse('admin:portal_document_add'), {
            'title': 'T', 'slug': 't', 'content': '<p>x</p>', 'category': category.pk,
            'status': Document.Status.DRAFT, 'author': other.pk,
        })
        self.assertEqual(Document.objects.get().author, other)

    def test_logs_are_read_only(self):
        entry = LogEntry.objects.create(
            user=self.user, object_repr='x', action_flag=1, change_message='hi'
        )
        self.assertEqual(self.client.get(reverse('admin:admin_logentry_add')).status_code, 403)
        change_url = reverse('admin:admin_logentry_change', args=[entry.pk])
        self.assertEqual(self.client.get(change_url).status_code, 200)
        self.assertEqual(self.client.post(change_url, {'change_message': 'edited'}).status_code, 403)
        delete_url = reverse('admin:admin_logentry_delete', args=[entry.pk])
        self.assertEqual(self.client.post(delete_url, {'post': 'yes'}).status_code, 403)

    def test_can_edit_site_settings(self):
        self.client.post(reverse('admin:portal_sitesetting_add'), {'key': 'name', 'value': 'News'})
        self.assertEqual(SiteSetting.objects.get().value, 'News')

    def test_is_staff_cannot_be_edited_by_hand(self):
        moderator = make_user(MODERATOR, username='moderator')
        url = reverse('admin:portal_user_change', args=[moderator.pk])
        self.assertNotIn('is_staff', self.form_for(url).fields)


class ReaderAdminTests(AdminTestCase):
    def test_is_sent_to_the_login_page(self):
        self.login()
        response = self.client.get(reverse('admin:portal_document_changelist'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)


STRONG_PASSWORD = 'plum-Harbor-917'


def published(author, **fields):
    return make_document(author, status=Document.Status.PUBLISHED, **fields)


def png_upload():
    buffer = io.BytesIO()
    Image.new('RGB', (2, 2)).save(buffer, 'PNG')
    return SimpleUploadedFile('photo.png', buffer.getvalue(), 'image/png')


class AccountApiTests(APITestCase):
    def register(self, **extra):
        return self.client.post('/api/auth/register', {
            'username': 'newuser', 'password': STRONG_PASSWORD, **extra,
        }, format='json')

    def test_register_logs_the_user_in(self):
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.client.get('/api/profile').data['username'], 'newuser')

    def test_register_never_returns_the_password(self):
        self.assertNotIn('password', self.register().data)

    def test_register_stores_a_hashed_password(self):
        self.register()
        user = User.objects.get(username='newuser')
        self.assertNotEqual(user.password, STRONG_PASSWORD)
        self.assertTrue(user.check_password(STRONG_PASSWORD))

    def test_register_ignores_privilege_fields(self):
        self.register(is_staff=True, is_superuser=True)
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_register_rejects_weak_password(self):
        response = self.register(password='12345')
        self.assertEqual(response.status_code, 400)
        self.assertIn('password', response.data)

    def test_register_rejects_duplicate_username(self):
        make_user(username='newuser')
        response = self.register()
        self.assertEqual(response.status_code, 400)
        self.assertIn('username', response.data)

    def test_login_and_logout(self):
        User.objects.create_user('someone', password=STRONG_PASSWORD)
        response = self.client.post('/api/auth/login', {
            'username': 'someone', 'password': STRONG_PASSWORD,
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/api/profile').status_code, 200)
        self.assertEqual(self.client.post('/api/auth/logout').status_code, 204)
        self.assertEqual(self.client.get('/api/profile').status_code, 403)

    def test_login_rejects_wrong_password(self):
        User.objects.create_user('someone', password=STRONG_PASSWORD)
        response = self.client.post('/api/auth/login', {
            'username': 'someone', 'password': 'wrong',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get('/api/profile').status_code, 403)


class CsrfApiTests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.user = User.objects.create_user('someone', password=STRONG_PASSWORD)
        self.credentials = {'username': 'someone', 'password': STRONG_PASSWORD}

    def token(self):
        return self.client.cookies['csrftoken'].value

    def test_login_needs_a_token(self):
        response = self.client.post('/api/auth/login', self.credentials, format='json')
        self.assertEqual(response.status_code, 403)

    def test_register_needs_a_token(self):
        response = self.client.post('/api/auth/register', {
            'username': 'x', 'password': STRONG_PASSWORD,
        }, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username='x').exists())

    def test_login_works_with_the_cookie_from_the_csrf_endpoint(self):
        self.client.get('/api/auth/csrf')
        response = self.client.post(
            '/api/auth/login', self.credentials, format='json',
            HTTP_X_CSRFTOKEN=self.token(),
        )
        self.assertEqual(response.status_code, 200)

    def test_logged_in_write_needs_a_token(self):
        document = published(self.user)
        self.client.force_login(self.user)
        url = f'/api/documents/{document.pk}/like'
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertFalse(Like.objects.exists())
        self.client.get('/api/auth/csrf')
        response = self.client.post(url, HTTP_X_CSRFTOKEN=self.token())
        self.assertEqual(response.status_code, 200)


class ProfileApiTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)

    def test_guest_is_rejected(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/profile').status_code, 403)
        response = self.client.patch('/api/profile', {'bio': 'x'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_edit_profile(self):
        response = self.client.patch(
            '/api/profile', {'display_name': 'New', 'bio': 'Hello'}, format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual((self.user.display_name, self.user.bio), ('New', 'Hello'))

    def test_upload_avatar(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as media:
            with self.settings(MEDIA_ROOT=media):
                response = self.client.patch(
                    '/api/profile', {'avatar': png_upload()}, format='multipart'
                )
        self.assertEqual(response.status_code, 200)
        self.assertIn('/media/avatars/', response.data['avatar'])

    def test_rejects_a_file_that_is_not_an_image(self):
        fake = SimpleUploadedFile('x.png', b'not an image', 'image/png')
        response = self.client.patch('/api/profile', {'avatar': fake}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_cannot_change_protected_fields(self):
        self.client.patch('/api/profile', {
            'username': 'hacked', 'is_staff': True, 'is_superuser': True,
        }, format='json')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'someone')
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_put_is_not_allowed(self):
        response = self.client.put('/api/profile', {'bio': 'x'}, format='json')
        self.assertEqual(response.status_code, 405)


class DocumentApiTests(APITestCase):
    def setUp(self):
        self.author = make_user(username='author')

    def test_list_returns_only_published(self):
        published(self.author, slug='live')
        make_document(self.author, slug='draft')
        make_document(self.author, slug='gone', status=Document.Status.UNPUBLISHED)
        response = self.client.get('/api/documents')
        self.assertEqual([d['slug'] for d in response.data['results']], ['live'])

    def test_list_has_summaries_but_not_full_content(self):
        published(self.author, summary='Short')
        result = self.client.get('/api/documents').data['results'][0]
        self.assertEqual(result['summary'], 'Short')
        self.assertNotIn('content', result)

    def test_list_is_paginated_newest_first(self):
        for number in range(12):
            published(self.author, slug=f'doc-{number}')
        first = self.client.get('/api/documents').data
        second = self.client.get('/api/documents?page=2').data
        self.assertEqual(first['count'], 12)
        self.assertEqual(len(first['results']), 10)
        self.assertEqual(len(second['results']), 2)
        self.assertEqual(first['results'][0]['slug'], 'doc-11')
        self.assertEqual(second['results'][-1]['slug'], 'doc-0')

    def test_page_past_the_end_is_404(self):
        self.assertEqual(self.client.get('/api/documents?page=9').status_code, 404)

    def test_detail_has_all_metadata(self):
        tag = Tag.objects.create(name='Tech', slug='tech')
        document = published(self.author, seo_title='SEO')
        document.tags.add(tag)
        data = self.client.get(f'/api/documents/{document.slug}').data
        self.assertEqual(data['content'], '<p>Body</p>')
        self.assertEqual(data['category']['slug'], 'news')
        self.assertEqual(data['author'], 'author')
        self.assertEqual(data['tags'][0]['slug'], 'tech')
        self.assertEqual(data['seo_title'], 'SEO')

    def test_detail_does_not_expose_the_author_email(self):
        User.objects.filter(pk=self.author.pk).update(email='private@example.com')
        document = published(self.author)
        response = self.client.get(f'/api/documents/{document.slug}')
        self.assertNotIn('private@example.com', response.content.decode())

    def test_draft_and_unpublished_are_404(self):
        draft = make_document(self.author, slug='draft')
        gone = make_document(self.author, slug='gone', status=Document.Status.UNPUBLISHED)
        for document in (draft, gone):
            with self.subTest(status=document.status):
                response = self.client.get(f'/api/documents/{document.slug}')
                self.assertEqual(response.status_code, 404)
                document.refresh_from_db()
                self.assertEqual(document.views_count, 0)

    def test_detail_adds_one_view(self):
        document = published(self.author)
        self.client.get(f'/api/documents/{document.slug}')
        response = self.client.get(f'/api/documents/{document.slug}')
        self.assertEqual(response.data['views_count'], 2)
        document.refresh_from_db()
        self.assertEqual(document.views_count, 2)

    def test_counting_a_view_does_not_touch_updated_at(self):
        document = published(self.author)
        before = document.updated_at
        self.client.get(f'/api/documents/{document.slug}')
        document.refresh_from_db()
        self.assertEqual(document.updated_at, before)

    def test_liked_flag_follows_the_session(self):
        document = published(self.author)
        reader = make_user()
        Like.objects.create(user=reader, document=document)
        guest = self.client.get(f'/api/documents/{document.slug}').data
        self.assertFalse(guest['liked'])
        self.assertEqual(guest['like_count'], 1)
        self.client.force_login(reader)
        self.assertTrue(self.client.get(f'/api/documents/{document.slug}').data['liked'])

    def test_user_tags_appear_once_each(self):
        document = published(self.author)
        tag = Tag.objects.create(name='Tech', slug='tech')
        UserTag.objects.create(user=self.author, document=document, tag=tag)
        UserTag.objects.create(user=make_user(), document=document, tag=tag)
        data = self.client.get(f'/api/documents/{document.slug}').data
        self.assertEqual([t['slug'] for t in data['user_tags']], ['tech'])

    def test_categories_and_tags_are_public(self):
        Category.objects.create(name='Sport', slug='sport')
        Tag.objects.create(name='Tech', slug='tech')
        self.assertEqual(self.client.get('/api/categories').data[0]['slug'], 'sport')
        self.assertEqual(self.client.get('/api/tags').data[0]['slug'], 'tech')

    def test_public_lists_are_read_only(self):
        for url in ('/api/documents', '/api/categories', '/api/tags'):
            with self.subTest(url=url):
                self.client.force_login(self.author)
                self.assertEqual(self.client.post(url, {}, format='json').status_code, 405)


class CommentApiTests(APITestCase):
    def setUp(self):
        self.reader = make_user()
        self.document = published(make_user(username='author'))
        self.url = f'/api/documents/{self.document.pk}/comments'

    def test_only_visible_comments_are_listed(self):
        Comment.objects.create(document=self.document, user=self.reader, body='Shown')
        Comment.objects.create(
            document=self.document, user=self.reader, body='Hidden',
            status=Comment.Status.HIDDEN,
        )
        results = self.client.get(self.url).data['results']
        self.assertEqual([c['body'] for c in results], ['Shown'])

    def test_guest_cannot_comment(self):
        response = self.client.post(self.url, {'body': 'Hi'}, format='json')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.objects.exists())

    def test_comment_uses_the_session_user(self):
        other = make_user(username='other')
        self.client.force_login(self.reader)
        response = self.client.post(self.url, {
            'body': 'Hi', 'user': other.pk, 'user_id': other.pk,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Comment.objects.get().user, self.reader)

    def test_cannot_set_status_when_commenting(self):
        self.client.force_login(self.reader)
        self.client.post(self.url, {'body': 'Hi', 'status': 'hidden'}, format='json')
        self.assertEqual(Comment.objects.get().status, Comment.Status.VISIBLE)

    def test_blank_and_overlong_comments_are_rejected(self):
        self.client.force_login(self.reader)
        for body in ('   ', 'x' * 2001):
            with self.subTest(length=len(body)):
                response = self.client.post(self.url, {'body': body}, format='json')
                self.assertEqual(response.status_code, 400)

    def test_comments_on_a_draft_are_404(self):
        draft = make_document(self.reader, slug='draft')
        url = f'/api/documents/{draft.pk}/comments'
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(url, {'body': 'Hi'}, format='json').status_code, 404)
        self.assertFalse(Comment.objects.exists())


class LikeApiTests(APITestCase):
    def setUp(self):
        self.reader = make_user()
        self.document = published(self.reader)
        self.url = f'/api/documents/{self.document.pk}/like'

    def test_guest_cannot_like(self):
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_toggle(self):
        self.client.force_login(self.reader)
        first = self.client.post(self.url).data
        self.assertEqual((first['liked'], first['like_count']), (True, 1))
        second = self.client.post(self.url).data
        self.assertEqual((second['liked'], second['like_count']), (False, 0))
        self.assertFalse(Like.objects.exists())

    def test_likes_are_per_user(self):
        Like.objects.create(user=make_user(username='other'), document=self.document)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(self.url).data['like_count'], 2)

    def test_like_on_a_draft_is_404(self):
        draft = make_document(self.reader, slug='draft')
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(f'/api/documents/{draft.pk}/like').status_code, 404)


class UserTagApiTests(APITestCase):
    def setUp(self):
        self.reader = make_user()
        self.document = published(self.reader)
        self.tag = Tag.objects.create(name='Tech', slug='tech')
        self.url = f'/api/documents/{self.document.pk}/tags'

    def test_guest_cannot_tag(self):
        response = self.client.post(self.url, {'tag': 'tech'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_add_tag_uses_the_session_user(self):
        self.client.force_login(self.reader)
        other = make_user(username='other')
        response = self.client.post(self.url, {'tag': 'tech', 'user': other.pk}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(UserTag.objects.get().user, self.reader)

    def test_adding_twice_keeps_one_row(self):
        self.client.force_login(self.reader)
        self.client.post(self.url, {'tag': 'tech'}, format='json')
        response = self.client.post(self.url, {'tag': 'tech'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(UserTag.objects.count(), 1)

    def test_readers_cannot_invent_tags(self):
        self.client.force_login(self.reader)
        response = self.client.post(self.url, {'tag': 'made-up'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Tag.objects.count(), 1)

    def test_tag_on_a_draft_is_404(self):
        draft = make_document(self.reader, slug='draft')
        self.client.force_login(self.reader)
        url = f'/api/documents/{draft.pk}/tags'
        self.assertEqual(self.client.post(url, {'tag': 'tech'}, format='json').status_code, 404)


class ReportApiTests(APITestCase):
    def setUp(self):
        self.reader = make_user()
        self.document = published(make_user(username='author'))
        self.comment = Comment.objects.create(
            document=self.document, user=self.reader, body='Spam'
        )
        self.url = f'/api/comments/{self.comment.pk}/report'

    def test_guest_cannot_report(self):
        response = self.client.post(self.url, {'reason': 'Spam'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_report_uses_the_session_user(self):
        other = make_user(username='other')
        self.client.force_login(self.reader)
        response = self.client.post(self.url, {
            'reason': 'Spam', 'reporter': other.pk, 'status': 'resolved',
            'resolved_by': other.pk,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        report = Report.objects.get()
        self.assertEqual(report.reporter, self.reader)
        self.assertEqual(report.status, Report.Status.OPEN)
        self.assertIsNone(report.resolved_by)

    def test_reason_is_required(self):
        self.client.force_login(self.reader)
        self.assertEqual(self.client.post(self.url, {}, format='json').status_code, 400)

    def test_same_user_cannot_report_twice_while_open(self):
        self.client.force_login(self.reader)
        self.client.post(self.url, {'reason': 'Spam'}, format='json')
        response = self.client.post(self.url, {'reason': 'Spam'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Report.objects.count(), 1)

    def test_hidden_comment_is_404(self):
        Comment.objects.update(status=Comment.Status.HIDDEN)
        self.client.force_login(self.reader)
        response = self.client.post(self.url, {'reason': 'Spam'}, format='json')
        self.assertEqual(response.status_code, 404)

    def test_comment_on_a_draft_is_404(self):
        Document.objects.update(status=Document.Status.DRAFT)
        self.client.force_login(self.reader)
        response = self.client.post(self.url, {'reason': 'Spam'}, format='json')
        self.assertEqual(response.status_code, 404)


class EveryRoleCanInteractTests(APITestCase):
    """The last row of the role table: comment, like, tag and report."""

    def test_every_role_including_reader(self):
        author = make_user(username='author')
        document = published(author)
        Tag.objects.create(name='Tech', slug='tech')
        for role in [*STAFF_ROLES, None]:
            with self.subTest(role=role):
                user = make_user(role, username=f'user-{role}')
                self.client.force_login(user)
                base = f'/api/documents/{document.pk}'
                comment = self.client.post(f'{base}/comments', {'body': 'Hi'}, format='json')
                self.assertEqual(comment.status_code, 201)
                self.assertEqual(self.client.post(f'{base}/like').status_code, 200)
                tag = self.client.post(f'{base}/tags', {'tag': 'tech'}, format='json')
                self.assertEqual(tag.status_code, 201)
                report = self.client.post(
                    f"/api/comments/{comment.data['id']}/report",
                    {'reason': 'Spam'}, format='json',
                )
                self.assertEqual(report.status_code, 201)


def on(year, month, day):
    return datetime.datetime(year, month, day, 12, tzinfo=datetime.timezone.utc)


class SearchTestCase(APITestCase):
    def setUp(self):
        self.author = make_user(username='author')

    def slugs(self, url):
        return [d['slug'] for d in self.client.get(url).data['results']]


class SearchFunctionTests(SearchTestCase):
    def test_takes_a_query_and_filters_and_returns_documents(self):
        document = published(self.author, title='Budget talks')
        self.assertEqual(list(search_documents('budget', {})), [document])

    def test_a_draft_never_appears_even_when_it_matches(self):
        make_document(self.author, slug='draft', title='Budget draft')
        make_document(
            self.author, slug='gone', title='Budget gone', status=Document.Status.UNPUBLISHED
        )
        self.assertEqual(list(search_documents('budget', {})), [])
        self.assertEqual(list(search_documents('', {})), [])


class SearchApiTests(SearchTestCase):
    def test_matches_title_and_body_ignoring_case(self):
        published(self.author, slug='in-title', title='Budget talks')
        published(self.author, slug='in-body', content='<p>The BUDGET rose</p>')
        published(self.author, slug='neither')
        self.assertCountEqual(self.slugs('/api/search?q=budget'), ['in-title', 'in-body'])

    def test_does_not_match_html_tags(self):
        published(self.author, content='<p><strong>Bold</strong> news</p>')
        self.assertEqual(self.slugs('/api/search?q=strong'), [])

    def test_draft_is_not_in_results(self):
        make_document(self.author, slug='draft', title='Budget draft')
        response = self.client.get('/api/search?q=budget')
        self.assertEqual(response.data['count'], 0)

    def test_percent_sign_is_not_a_wildcard(self):
        published(self.author, title='Budget')
        self.assertEqual(self.slugs('/api/search?q=%25'), [])

    def test_category_filter(self):
        sport = Category.objects.create(name='Sport', slug='sport')
        Document.objects.create(
            title='Budget', slug='in-sport', content='<p>x</p>', category=sport,
            author=self.author, status=Document.Status.PUBLISHED,
        )
        published(self.author, slug='in-news', title='Budget')
        self.assertEqual(self.slugs('/api/search?q=budget&category=sport'), ['in-sport'])

    def test_tag_filter(self):
        tag = Tag.objects.create(name='Tech', slug='tech')
        published(self.author, slug='tagged', title='Budget').tags.add(tag)
        published(self.author, slug='plain', title='Budget')
        self.assertEqual(self.slugs('/api/search?q=budget&tag=tech'), ['tagged'])

    def test_date_filter_includes_both_ends(self):
        published(self.author, slug='before', published_at=on(2026, 1, 1))
        published(self.author, slug='start', published_at=on(2026, 2, 1))
        published(self.author, slug='end', published_at=on(2026, 3, 1))
        published(self.author, slug='after', published_at=on(2026, 4, 1))
        self.assertEqual(
            self.slugs('/api/search?from=2026-02-01&to=2026-03-01'), ['end', 'start']
        )

    def test_filters_combine(self):
        tag = Tag.objects.create(name='Tech', slug='tech')
        published(
            self.author, slug='match', title='Budget', published_at=on(2026, 2, 1)
        ).tags.add(tag)
        published(
            self.author, slug='too-old', title='Budget', published_at=on(2025, 2, 1)
        ).tags.add(tag)
        published(self.author, slug='no-tag', title='Budget', published_at=on(2026, 2, 1))
        url = '/api/search?q=budget&category=news&tag=tech&from=2026-01-01'
        self.assertEqual(self.slugs(url), ['match'])

    def test_filters_work_without_a_keyword(self):
        tag = Tag.objects.create(name='Tech', slug='tech')
        published(self.author, slug='tagged').tags.add(tag)
        published(self.author, slug='plain')
        self.assertEqual(self.slugs('/api/search?tag=tech'), ['tagged'])

    def test_unknown_filter_values_find_nothing(self):
        published(self.author)
        self.assertEqual(self.slugs('/api/search?category=missing'), [])
        self.assertEqual(self.slugs('/api/search?tag=missing'), [])

    def test_bad_dates_are_rejected_without_logging(self):
        for value in ('not-a-date', '2026-02-31'):
            with self.subTest(value=value):
                response = self.client.get(f'/api/search?from={value}')
                self.assertEqual(response.status_code, 400)
                self.assertIn('from', response.data)
        self.assertFalse(SearchClickLog.objects.exists())

    def test_nul_character_does_not_crash(self):
        published(self.author, title='Budget')
        response = self.client.get('/api/search?q=Budg%00et&category=%00&tag=%00')
        self.assertEqual(response.status_code, 200)

    def test_results_are_paginated(self):
        for number in range(12):
            published(self.author, slug=f'doc-{number}', title='Budget')
        first = self.client.get('/api/search?q=budget').data
        second = self.client.get('/api/search?q=budget&page=2').data
        self.assertEqual(first['count'], 12)
        self.assertEqual(len(first['results']), 10)
        self.assertEqual(len(second['results']), 2)


class SearchLoggingTests(SearchTestCase):
    def search(self, url='/api/search?q=budget'):
        return self.client.get(url).data

    def click(self, query_id, document, position, **extra):
        return self.client.post('/api/search/click', {
            'query_id': str(query_id), 'document': document.pk, 'position': position, **extra,
        }, format='json')

    def test_one_search_and_one_click_make_two_rows_sharing_a_query_id(self):
        document = published(self.author, title='Budget talks')
        query_id = self.search()['query_id']
        self.assertEqual(self.click(query_id, document, 1).status_code, 201)

        rows = SearchClickLog.objects.order_by('id')
        self.assertEqual(rows.count(), 2)
        search_row, click_row = rows
        self.assertEqual(search_row.query_id, query_id)
        self.assertEqual(click_row.query_id, query_id)
        self.assertIsNone(search_row.clicked_doc)
        self.assertIsNone(search_row.position)
        self.assertEqual(search_row.query_string, 'budget')
        self.assertEqual(search_row.result_count, 1)
        self.assertEqual(click_row.clicked_doc, document)
        self.assertEqual(click_row.position, 1)
        self.assertEqual(click_row.query_string, 'budget')

    def test_each_new_search_gets_its_own_query_id(self):
        first = self.search()['query_id']
        second = self.search()['query_id']
        self.assertNotEqual(first, second)
        self.assertEqual(SearchClickLog.objects.count(), 2)

    def test_later_pages_keep_the_query_id_and_log_nothing(self):
        for number in range(12):
            published(self.author, slug=f'doc-{number}', title='Budget')
        query_id = self.search()['query_id']
        second = self.search(f'/api/search?q=budget&page=2&query_id={query_id}')
        self.assertEqual(second['query_id'], query_id)
        self.assertEqual(SearchClickLog.objects.count(), 1)

    def test_position_counts_across_pages(self):
        for number in range(12):
            published(self.author, slug=f'doc-{number}', title='Budget')
        document = Document.objects.get(slug='doc-0')
        query_id = self.search()['query_id']
        self.assertEqual(self.click(query_id, document, 12).status_code, 201)
        self.assertEqual(SearchClickLog.objects.get(position=12).clicked_doc, document)

    def test_made_up_query_id_on_search_starts_a_new_search(self):
        made_up = uuid.uuid4()
        for value in (made_up, 'not-a-uuid'):
            with self.subTest(value=value):
                data = self.search(f'/api/search?q=budget&query_id={value}')
                self.assertNotEqual(str(data['query_id']), str(value))
        self.assertEqual(SearchClickLog.objects.count(), 2)

    def test_reusing_a_query_id_for_other_words_starts_a_new_search(self):
        query_id = self.search()['query_id']
        data = self.search(f'/api/search?q=other&query_id={query_id}')
        self.assertNotEqual(data['query_id'], query_id)
        self.assertEqual(SearchClickLog.objects.count(), 2)

    def test_page_past_the_end_logs_nothing(self):
        response = self.client.get('/api/search?q=budget&page=9')
        self.assertEqual(response.status_code, 404)
        self.assertFalse(SearchClickLog.objects.exists())

    def test_zero_result_search_is_logged(self):
        self.search('/api/search?q=nothing')
        row = SearchClickLog.objects.get()
        self.assertEqual((row.query_string, row.result_count), ('nothing', 0))

    def test_guest_rows_have_no_user(self):
        document = published(self.author, title='Budget')
        self.click(self.search()['query_id'], document, 1)
        self.assertFalse(SearchClickLog.objects.filter(user__isnull=False).exists())

    def test_logged_in_rows_use_the_session_user(self):
        reader = make_user()
        other = make_user(username='other')
        document = published(self.author, title='Budget')
        self.client.force_login(reader)
        query_id = self.search()['query_id']
        self.click(query_id, document, 1, user=other.pk, user_id=other.pk)
        self.assertEqual(SearchClickLog.objects.filter(user=reader).count(), 2)

    def test_click_cannot_change_the_query_string(self):
        document = published(self.author, title='Budget')
        query_id = self.search()['query_id']
        self.click(query_id, document, 1, query_string='forged')
        self.assertFalse(SearchClickLog.objects.filter(query_string='forged').exists())

    def test_unknown_query_id_is_404(self):
        document = published(self.author)
        self.assertEqual(self.click(uuid.uuid4(), document, 1).status_code, 404)

    def test_click_on_a_draft_is_rejected(self):
        published(self.author, slug='live', title='Budget')
        draft = make_document(self.author, slug='draft')
        response = self.click(self.search()['query_id'], draft, 1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(SearchClickLog.objects.count(), 1)

    def test_impossible_positions_are_rejected(self):
        document = published(self.author, title='Budget')
        query_id = self.search()['query_id']
        for position in (0, -1, 2):
            with self.subTest(position=position):
                self.assertEqual(self.click(query_id, document, position).status_code, 400)
        self.assertEqual(SearchClickLog.objects.count(), 1)

    def test_a_second_click_adds_another_row(self):
        document = published(self.author, title='Budget')
        query_id = self.search()['query_id']
        self.click(query_id, document, 1)
        self.assertEqual(self.click(query_id, document, 1).status_code, 201)
        self.assertEqual(SearchClickLog.objects.filter(query_id=query_id).count(), 3)


class AnalyticsAccessTests(TestCase):
    def get_as(self, role):
        self.client.force_login(make_user(role))
        return self.client.get(reverse('analytics'))

    def test_allowed_roles(self):
        for role in (DATA_SEO, SUPER_ADMIN):
            with self.subTest(role=role):
                self.assertEqual(self.get_as(role).status_code, 200)
                User.objects.all().delete()

    def test_other_roles_get_403(self):
        for role in (CONTENT_MANAGER, MODERATOR, None):
            with self.subTest(role=role):
                self.assertEqual(self.get_as(role).status_code, 403)
                User.objects.all().delete()

    def test_guest_goes_to_the_admin_login(self):
        response = self.client.get(reverse('analytics'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response.url)

    def test_admin_home_links_to_it_for_allowed_roles(self):
        link = reverse('analytics')
        self.client.force_login(make_user(DATA_SEO))
        self.assertContains(self.client.get(reverse('admin:index')), link)

    def test_admin_home_hides_the_link_from_other_roles(self):
        link = reverse('analytics')
        self.client.force_login(make_user(MODERATOR))
        self.assertNotContains(self.client.get(reverse('admin:index')), link)


class AnalyticsNumbersTests(TestCase):
    def setUp(self):
        self.author = make_user(username='author')
        self.client.force_login(make_user(DATA_SEO))

    def dashboard(self):
        return self.client.get(reverse('analytics')).context

    def log(self, query, result_count=1, **fields):
        return SearchClickLog.objects.create(
            query_string=query, query_id=uuid.uuid4(), result_count=result_count, **fields
        )

    def test_empty_site_shows_zero(self):
        response = self.client.get(reverse('analytics'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_views'], 0)
        self.assertContains(response, 'No searches yet.')

    def test_total_views_adds_every_document(self):
        published(self.author, slug='a', views_count=3)
        published(self.author, slug='b', views_count=4)
        self.assertEqual(self.dashboard()['total_views'], 7)

    def test_most_viewed_is_ordered_and_skips_unread(self):
        published(self.author, slug='low', views_count=1)
        published(self.author, slug='high', views_count=9)
        published(self.author, slug='none')
        slugs = [d.slug for d in self.dashboard()['most_viewed']]
        self.assertEqual(slugs, ['high', 'low'])

    def test_lists_stop_at_ten(self):
        for number in range(12):
            published(self.author, slug=f'doc-{number}', views_count=1)
            self.log(f'query {number}', result_count=0)
        context = self.dashboard()
        self.assertEqual(len(context['most_viewed']), 10)
        self.assertEqual(len(context['top_queries']), 10)
        self.assertEqual(len(context['zero_result_queries']), 10)

    def test_top_queries_ignore_case(self):
        self.log('Budget')
        self.log('budget')
        self.log('sport')
        rows = list(self.dashboard()['top_queries'])
        self.assertEqual(rows[0], {'query': 'budget', 'total': 2})
        self.assertEqual(rows[1], {'query': 'sport', 'total': 1})

    def test_top_queries_skip_filter_only_searches(self):
        self.log('')
        self.assertEqual(list(self.dashboard()['top_queries']), [])

    def test_clicks_are_not_counted_as_searches(self):
        document = published(self.author)
        search = self.log('budget', result_count=0)
        SearchClickLog.objects.create(
            query_string='budget', query_id=search.query_id, clicked_doc=document, position=1
        )
        context = self.dashboard()
        self.assertEqual(context['top_queries'][0]['total'], 1)
        self.assertEqual(context['zero_result_queries'][0]['total'], 1)

    def test_zero_result_queries_only_list_empty_searches(self):
        self.log('found', result_count=3)
        self.log('Missing', result_count=0)
        self.assertEqual(
            list(self.dashboard()['zero_result_queries']), [{'query': 'missing', 'total': 1}]
        )

    def test_click_on_a_deleted_document_is_not_a_zero_result_search(self):
        document = published(self.author)
        SearchClickLog.objects.create(
            query_string='budget', query_id=uuid.uuid4(), clicked_doc=document, position=1
        )
        document.delete()
        context = self.dashboard()
        self.assertEqual(list(context['zero_result_queries']), [])
        self.assertEqual(list(context['top_queries']), [])

    def test_most_clicked_is_ordered(self):
        one = published(self.author, slug='one')
        two = published(self.author, slug='two')
        published(self.author, slug='never')
        for document, clicks in ((one, 1), (two, 2)):
            for _ in range(clicks):
                self.log('x', clicked_doc=document, position=1)
        rows = [(d.slug, d.clicks) for d in self.dashboard()['most_clicked']]
        self.assertEqual(rows, [('two', 2), ('one', 1)])

    def test_query_text_is_escaped_on_the_page(self):
        self.log('<script>alert(1)</script>')
        response = self.client.get(reverse('analytics'))
        self.assertNotContains(response, '<script>alert(1)</script>')
        self.assertContains(response, '&lt;script&gt;alert(1)&lt;/script&gt;')

    def test_numbers_change_after_using_the_site(self):
        document = published(self.author, title='Budget talks')
        before = self.dashboard()
        self.assertEqual(before['total_views'], 0)
        self.assertEqual(list(before['top_queries']), [])

        site = APIClient()
        query_id = site.get('/api/search?q=budget').data['query_id']
        site.get('/api/search?q=nothing-here')
        site.post('/api/search/click', {
            'query_id': str(query_id), 'document': document.pk, 'position': 1,
        }, format='json')
        site.get(f'/api/documents/{document.slug}')

        after = self.dashboard()
        self.assertEqual(after['total_views'], 1)
        self.assertEqual(after['most_viewed'][0], document)
        self.assertIn({'query': 'budget', 'total': 1}, list(after['top_queries']))
        self.assertEqual(
            list(after['zero_result_queries']), [{'query': 'nothing-here', 'total': 1}]
        )
        self.assertEqual(after['most_clicked'][0], document)


class ArticlesFileTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.articles = json.loads(ARTICLES_FILE.read_text(encoding='utf-8'))

    def test_has_100_articles_across_six_categories(self):
        self.assertEqual(len(self.articles), 100)
        categories = collections.Counter(a['category'] for a in self.articles)
        self.assertEqual(len(categories), 6)

    def test_every_article_is_150_to_300_words(self):
        for article in self.articles:
            with self.subTest(title=article['title']):
                words = len(' '.join(article['paragraphs']).split())
                self.assertTrue(150 <= words <= 300, words)

    def test_every_article_has_a_summary_and_tags(self):
        for article in self.articles:
            with self.subTest(title=article['title']):
                self.assertTrue(article['summary'])
                self.assertTrue(article['tags'])

    def test_titles_are_unique(self):
        titles = [a['title'] for a in self.articles]
        self.assertEqual(len(titles), len(set(titles)))

    def test_no_placeholder_text(self):
        text = ARTICLES_FILE.read_text(encoding='utf-8').lower()
        self.assertNotIn('lorem', text)
        self.assertNotIn('ipsum', text)


class SeedDataTests(TestCase):
    def counts(self):
        models = (
            Category, Comment, Document, Like, Report, SearchClickLog,
            SiteSetting, Tag, User, UserTag,
        )
        return {model.__name__: model.objects.count() for model in models}

    def seed(self):
        call_command('seed_data', stdout=io.StringIO())

    def setUp(self):
        media = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(media.cleanup)
        override = self.settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

    def test_loads_everything_and_a_rerun_adds_nothing(self):
        self.seed()
        first = self.counts()
        self.assertEqual(first['Document'], 100)
        self.assertEqual(first['Category'], 6)
        self.assertEqual(first['User'], 6)
        self.assertGreater(first['Comment'], 50)
        self.assertGreater(first['Like'], 50)
        self.assertGreater(first['UserTag'], 0)
        self.assertEqual(first['Report'], 5)
        self.assertGreater(first['SearchClickLog'], 50)

        comment = Comment.objects.first()
        Comment.objects.filter(pk=comment.pk).update(status=Comment.Status.HIDDEN)
        self.seed()
        self.assertEqual(self.counts(), first)
        comment.refresh_from_db()
        self.assertEqual(comment.status, Comment.Status.HIDDEN)

    def test_accounts_have_their_roles_and_demo_password(self):
        self.seed()
        for username, _, role in ACCOUNTS:
            with self.subTest(username=username):
                user = authenticate(username=username, password=DEMO_PASSWORD)
                self.assertIsNotNone(user)
                self.assertEqual(user.is_staff, role is not None)
                self.assertEqual(
                    list(user.groups.values_list('name', flat=True)), [role] if role else []
                )

    def test_documents_are_clean_and_complete(self):
        self.seed()
        self.assertGreaterEqual(Document.objects.filter(status='published').count(), 50)
        self.assertTrue(Document.objects.filter(status='draft').exists())
        self.assertTrue(Document.objects.filter(status='unpublished').exists())
        for document in Document.objects.all():
            with self.subTest(slug=document.slug):
                self.assertTrue(document.content_text)
                self.assertNotIn('<', document.content_text)
                self.assertTrue(document.summary)
                self.assertTrue(document.image)
                self.assertTrue(document.image_alt)
                self.assertTrue(document.tags.exists())
                self.assertEqual(document.status == 'draft', document.published_at is None)

    def test_rerun_draws_banners_that_went_missing(self):
        self.seed()
        document = Document.objects.first()
        document.image.storage.delete(document.image.name)
        self.seed()
        document.refresh_from_db()
        self.assertTrue(document.image.storage.exists(document.image.name))

    def test_search_logs_fill_the_dashboard(self):
        self.seed()
        self.client.force_login(User.objects.get(username='seo'))
        context = self.client.get(reverse('analytics')).context
        self.assertGreater(context['total_views'], 0)
        self.assertEqual(context['top_queries'][0]['query'], 'harbour')
        self.assertEqual(context['top_queries'][0]['total'], 12)
        zero = {row['query'] for row in context['zero_result_queries']}
        self.assertEqual(zero, {'time machine', 'moon base', 'dragon sightings'})
        self.assertTrue(context['most_clicked'])
