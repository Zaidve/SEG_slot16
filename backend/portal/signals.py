from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .indexing import index_document
from .models import Document, User
from .roles import STAFF_ROLES


@receiver(post_save, sender=Document)
def update_search_index(instance, **kwargs):
    """Every save goes through here, so publishing and unpublishing take effect at once.

    View counts use QuerySet.update(), which skips this, so reading an
    article does not reindex it. Deleting a document cascades to its postings.
    """
    index_document(instance)


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
