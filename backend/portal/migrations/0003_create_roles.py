from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations


def crud(model):
    return [f'portal.{action}_{model}' for action in ('add', 'change', 'delete', 'view')]


# Super Admin is not listed: that role gets every permission.
ROLE_PERMISSIONS = {
    'Content Manager': [
        *crud('document'),
        *crud('category'),
        *crud('tag'),
        'portal.publish_document',
        'portal.edit_seo',
    ],
    'Moderator': [
        'portal.view_comment',
        'portal.change_comment',
        'portal.view_report',
        'portal.change_report',
    ],
    'Data & SEO': [
        'portal.view_document',
        'portal.edit_seo',
        'portal.view_analytics',
    ],
}


def create_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')

    # Django normally creates permissions after all migrations finish,
    # so on a fresh database they do not exist yet. Create them now.
    for label in ('contenttypes', 'auth', 'admin', 'sessions', 'portal'):
        create_permissions(global_apps.get_app_config(label), apps=apps, verbosity=0)

    super_admin, _ = Group.objects.get_or_create(name='Super Admin')
    super_admin.permissions.set(Permission.objects.all())

    for role, permissions in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role)
        for permission in permissions:
            app_label, codename = permission.split('.')
            group.permissions.add(
                Permission.objects.get(
                    content_type__app_label=app_label, codename=codename
                )
            )


def delete_roles(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=['Super Admin', *ROLE_PERMISSIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('admin', '0003_logentry_add_action_flag_choices'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('sessions', '0001_initial'),
        ('portal', '0002_custom_permissions'),
    ]

    operations = [
        migrations.RunPython(create_roles, delete_roles),
    ]
