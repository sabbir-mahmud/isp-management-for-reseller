"""Customer lifecycle operations that touch more than one model."""

import logging

from django.db import transaction

from apps.warehouse.models import Onu

logger = logging.getLogger(__name__)


class ProvisioningError(Exception):
    pass


@transaction.atomic
def assign_onu(client, onu: Onu | None, *, actor=None) -> None:
    """Attach (or detach) an ONU, keeping the device's status honest.

    The device status and the client link used to be edited independently,
    which let an ONU read "in stock" while sitting in someone's living room.
    """
    previous = client.onu
    if previous and previous.pk != getattr(onu, "pk", None):
        previous.status = Onu.Status.IN_STOCK
        previous.updated_by = actor
        previous.save(update_fields=["status", "updated_by", "updated_at"])

    if onu is None:
        client.onu = None
        client.save(update_fields=["onu", "updated_at"])
        return

    conflict = Onu.objects.filter(pk=onu.pk).exclude(client__pk=client.pk).first()
    if conflict and getattr(conflict, "client", None) is not None:
        raise ProvisioningError(f"ONU {onu.serial} is already assigned to another client.")
    if onu.status in {Onu.Status.FAULTY, Onu.Status.RETIRED}:
        raise ProvisioningError(f"ONU {onu.serial} is marked {onu.get_status_display()}.")

    client.onu = onu
    client.save(update_fields=["onu", "updated_at"])
    onu.status = Onu.Status.ASSIGNED
    onu.updated_by = actor
    onu.save(update_fields=["status", "updated_by", "updated_at"])


@transaction.atomic
def set_client_status(client, status: str, *, actor=None):
    """Change a client's status, releasing hardware when they terminate."""
    from .models import Client

    client.status = status
    client.updated_by = actor
    client.save(update_fields=["status", "updated_by", "updated_at"])

    if status == Client.Status.TERMINATED:
        subscription = client.subscription
        if subscription:
            subscription.cancel()
        if client.onu:
            assign_onu(client, None, actor=actor)
    logger.info("client %s status -> %s", client.client_code, status)
    return client
