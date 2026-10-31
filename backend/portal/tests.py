import io
import tempfile

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from .models import Category, Comment, Document, Report, SiteSetting, Tag, User
from .roles import CONTENT_MANAGER, DATA_SEO, MODERATOR, STAFF_ROLES, SUPER_ADMIN


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
    fields.setdefault('slug', 'a-title')
    return Document.objects.create(
        title='A title', content='<p>Body</p>', category=category, author=author, **fields
    )


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
