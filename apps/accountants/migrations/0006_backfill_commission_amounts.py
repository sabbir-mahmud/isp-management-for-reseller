"""Restate existing invoices and payments under the new commission columns.

Everything billed before this change was collected by the reseller — that was
the only arrangement the system could express — so those rows keep that mode.
The commission rate is taken from the settings row in force, and the split is
computed with the same helper the application uses, so history and new
records agree to the paisa.
"""

from decimal import Decimal

from django.db import migrations

from apps.core.utils import split_commission


def forwards(apps, schema_editor):
    BillingSettings = apps.get_model("accountants", "BillingSettings")
    Invoice = apps.get_model("accountants", "Invoice")
    Payment = apps.get_model("accountants", "Payment")

    settings_row = BillingSettings.objects.first()
    rate = settings_row.commission_percent if settings_row else Decimal("20.00")

    for invoice in Invoice.objects.all().iterator():
        invoice.collection_mode = "reseller"
        invoice.commission_percent = rate
        invoice.commission_amount, invoice.upstream_amount = split_commission(invoice.total, rate)
        invoice.save(
            update_fields=[
                "collection_mode",
                "commission_percent",
                "commission_amount",
                "upstream_amount",
            ]
        )

    for payment in Payment.objects.select_related("invoice").iterator():
        payment.collection_mode = payment.invoice.collection_mode
        payment.commission_amount, payment.upstream_amount = split_commission(
            payment.amount, payment.invoice.commission_percent
        )
        payment.save(update_fields=["collection_mode", "commission_amount", "upstream_amount"])


def backwards(apps, schema_editor):
    """Nothing to undo: the columns themselves are removed by the migration above."""


class Migration(migrations.Migration):
    dependencies = [
        ("accountants", "0005_collection_modes_and_settlements"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
