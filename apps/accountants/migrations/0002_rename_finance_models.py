"""Rename the finance models to accounting words.

`Invest` was money going out (an expense) and `Earn` money coming in;
`Commission` was really the single settings row for the billing engine.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accountants", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(old_name="Invest", new_name="Expense"),
        migrations.RenameModel(old_name="Earn", new_name="Income"),
        migrations.RenameModel(old_name="Commission", new_name="BillingSettings"),
        migrations.RenameField("expense", old_name="invest_details", new_name="description"),
        migrations.RenameField("expense", old_name="invest_amount", new_name="amount"),
        migrations.RenameField("expense", old_name="created", new_name="created_at"),
        migrations.RenameField("income", old_name="earn_details", new_name="description"),
        migrations.RenameField("income", old_name="earn_amount", new_name="amount"),
        migrations.RenameField("income", old_name="created", new_name="created_at"),
        migrations.RenameField("billingsettings", old_name="commission", new_name="commission_percent"),
    ]
