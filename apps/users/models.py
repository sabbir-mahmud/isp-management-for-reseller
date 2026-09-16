"""Staff accounts and what each of them is allowed to touch.

Roles are not checked directly in views. Each role maps to a Django `Group`
carrying real model permissions (see `roles.py`), so `user.has_perm(...)`,
the admin, and the API all agree on one answer.
"""

from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    MANAGER = "manager", "Manager"
    ACCOUNTANT = "accountant", "Accountant"
    SUPPORT = "support", "Support"


class Profile(TimeStampedModel):
    """One-to-one extension of the built-in user.

    A custom `AUTH_USER_MODEL` would have been the textbook choice, but this
    project already has an `auth_user` table in the wild; swapping the user
    model after the first migration is a known one-way door. A profile gets
    the same result without the migration hazard.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.SUPPORT, db_index=True
    )
    phone = models.CharField(max_length=20, blank=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["user__username"]
        verbose_name = "staff profile"
        verbose_name_plural = "staff profiles"

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER
