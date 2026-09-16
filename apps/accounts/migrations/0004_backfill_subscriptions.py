"""Carry the old shape into the new one, then drop the columns it lived in.

Runs before the removals below it, so nothing is dropped until its contents
have a new home:

  * every client gets a `client_code`;
  * `Clients.pack` becomes a `Subscription` carrying the price that was in
    force, so future re-pricing of a package cannot rewrite history;
  * `Package.speed/ggc/fna` were free text ("20 Mbps", "10mb") — the digits
    are pulled out into the new integer columns and anything unparseable is
    left at 0 for an operator to correct.
"""

import re

import django.core.validators
from django.db import migrations, models


def _first_number(value) -> int:
    """Pull the leading number out of a free-text speed, else 0."""
    match = re.search(r"\d+", str(value or ""))
    return int(match.group()) if match else 0


def forwards(apps, schema_editor):
    Package = apps.get_model("accounts", "Package")
    Client = apps.get_model("accounts", "Client")
    Subscription = apps.get_model("accounts", "Subscription")

    for package in Package.objects.all():
        package.bandwidth_mbps = _first_number(package.speed)
        package.ggc_mbps = _first_number(package.ggc)
        package.fna_mbps = _first_number(package.fna)
        package.save(update_fields=["bandwidth_mbps", "ggc_mbps", "fna_mbps"])

    for index, client in enumerate(Client.objects.order_by("id"), start=1):
        updates = []
        if not client.client_code:
            client.client_code = f"C-{index:06d}"
            updates.append("client_code")
        if updates:
            client.save(update_fields=updates)

        if client.pack_id and not Subscription.objects.filter(client=client).exists():
            Subscription.objects.create(
                client=client,
                package_id=client.pack_id,
                monthly_price=client.pack.monthly_price,
                discount=0,
                start_date=client.created_at.date() if client.created_at else None,
                status="active" if client.status == "active" else "cancelled",
                created_at=client.created_at,
            )


def backwards(apps, schema_editor):
    """Put the package reference back; the free-text speeds cannot be restored."""
    Client = apps.get_model("accounts", "Client")
    Subscription = apps.get_model("accounts", "Subscription")
    for subscription in Subscription.objects.filter(status="active").select_related("client"):
        Client.objects.filter(pk=subscription.client_id).update(pack_id=subscription.package_id)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_subscriptions_and_client_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="client", name="pack"),
        migrations.RemoveField(model_name="package", name="speed"),
        migrations.RemoveField(model_name="package", name="ggc"),
        migrations.RemoveField(model_name="package", name="fna"),
        # The codes exist now, so the column can carry its real definition.
        migrations.AlterField(
            model_name="client",
            name="client_code",
            field=models.CharField(
                editable=False,
                help_text="Auto-assigned, e.g. C-000123.",
                max_length=20,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="package",
            name="bandwidth_mbps",
            field=models.PositiveIntegerField(
                help_text="Committed speed in Mbps.",
                validators=[django.core.validators.MinValueValidator(1)],
            ),
        ),
    ]
