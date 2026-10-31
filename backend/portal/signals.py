from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import User
from .roles import STAFF_ROLES


@receiver(m2m_changed, sender=User.groups.through)
def sync_staff_access(instance, action, reverse, pk_set, **kwargs):
    """Give is_staff to users in a staff role, and take it away when they leave."""
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return
    # reverse means the change came from the group side: group.user_set.add(user).
    users = User.objects.filter(pk__in=pk_set or []) if reverse else [instance]
    for user in users:
        in_staff_role = user.groups.filter(name__in=STAFF_ROLES).exists()
        user.is_staff = user.is_superuser or in_staff_role
        user.save(update_fields=['is_staff'])
