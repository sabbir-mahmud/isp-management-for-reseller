"""Rename inventory fields to what they actually hold.

Renames rather than drop/add so existing stock data survives the redesign.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("warehouse", "0001_initial"),
    ]

    operations = [
        migrations.RenameField("pop", old_name="main_pop_name", new_name="parent"),
        migrations.RenameField("product", old_name="price", new_name="unit_price"),
        migrations.RenameField("product", old_name="serial", new_name="sku"),
        migrations.RenameField("onu", old_name="price", new_name="purchase_price"),
    ]
