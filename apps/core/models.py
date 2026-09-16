"""Abstract building blocks shared by every domain app.

Nothing here maps to a table of its own; these exist so that auditing,
soft-deletion and money handling are decided once instead of per model.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


def money_field(**kwargs):
    """A currency amount.

    Always `Decimal`, never `float` — binary floats silently lose paisa on
    every sum, and this system exists to add money up.
    """
    kwargs.setdefault("max_digits", 12)
    kwargs.setdefault("decimal_places", 2)
    kwargs.setdefault("default", Decimal("0.00"))
    return models.DecimalField(**kwargs)


class TimeStampedModel(models.Model):
    """Created/updated stamps on every row."""

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


class ActorStampedModel(TimeStampedModel):
    """Adds "who did it" to the timestamps.

    The FKs are nullable and `SET_NULL`: losing an operator account must never
    take financial history with it.
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="%(app_label)s_%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        editable=False,
        related_name="%(app_label)s_%(class)s_updated",
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        """Soft-delete in bulk (queryset-level `.delete()` bypasses `Model.delete`)."""
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager that hides soft-deleted rows."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(models.Model):
    """Rows that are retired rather than destroyed.

    A client who leaves is still attached to last year's invoices; deleting the
    row would corrupt the books. `objects` hides them, `all_objects` does not.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=["deleted_at"])
        return (1, {self._meta.label: 1})

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])
