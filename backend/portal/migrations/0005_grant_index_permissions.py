from django.apps import apps as global_apps
from django.contrib.auth.management import create_permissions
from django.db import migrations


def grant_to_super_admin(apps, schema_editor):
    """Super Admin has every permission, including those for the new index tables."""
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    # As in 0003: on a fresh database the new permissions do not exist yet.
    create_permissions(global_apps.get_app_config('portal'), apps=apps, verbosity=0)
    Group.objects.get(name='Super Admin').permissions.add(
        *Permission.objects.filter(
            content_type__app_label='portal',
            content_type__model__in=['indexeddocument', 'posting'],
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ('portal', '0004_search_index'),
    ]

    operations = [
        migrations.RunPython(grant_to_super_admin, migrations.RunPython.noop),
    ]
