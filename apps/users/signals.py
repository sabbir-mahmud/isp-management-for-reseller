"""Keep auth state consistent without anyone having to remember to."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.management import create_permissions
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import Profile, Role
from .roles import apply_role, sync_roles


@receiver(post_save, sender=get_user_model())
def ensure_profile(sender, instance, created, **kwargs):
    """Every user has a profile.

    Superusers created by `createsuperuser` get the Owner role; everyone else
    starts at the least-privileged role and is promoted deliberately.
    """
    if not created:
        return
    role = Role.OWNER if instance.is_superuser else Role.SUPPORT
    Profile.objects.get_or_create(user=instance, defaults={"role": role})
    apply_role(instance, role)


@receiver(post_save, sender=Profile)
def sync_group_on_role_change(sender, instance, **kwargs):
    apply_role(instance.user, instance.role)


@receiver(post_migrate)
def sync_roles_after_migrate(sender, using=None, **kwargs):
    """Rebuild the role groups after a migrate.

    Gated on this app so it runs once per `migrate` rather than once per
    installed app. Django creates each app's permissions in its own
    `post_migrate` handler, and the order those fire in depends on
    `INSTALLED_APPS`, so the permissions this app needs are created here
    first instead of being assumed to exist.
    """
    if getattr(sender, "name", None) != "apps.users":
        return

    for app_config in apps.get_app_configs():
        if app_config.models_module is not None:
            create_permissions(app_config, using=using, verbosity=0)
    sync_roles()
