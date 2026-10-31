from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from .models import User
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


def make_user(role=None):
    user = User.objects.create_user('someone')
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
