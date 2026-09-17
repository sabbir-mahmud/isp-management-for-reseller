"""Turn the Month/Year lookup rows into real dates, then retire them.

The old ledger stored its period as two foreign keys to tables of free text
("September", "2024"). Nothing could order, range over or group by that. Here
each row's `occurred_on` is rebuilt from those names before the columns and
the two lookup tables go away.
"""

import calendar
import datetime

from django.db import migrations

MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})


def _to_date(month_name, year_name, fallback):
    """Best-effort ("September", "2024") -> date(2024, 9, 1)."""
    month = MONTHS.get(str(month_name or "").strip().lower())
    try:
        year = int(str(year_name).strip())
    except (TypeError, ValueError):
        year = None
    if month and year:
        return datetime.date(year, month, 1)
    # Unparseable: keep the row's own creation date rather than invent one.
    return fallback


def forwards(apps, schema_editor):
    for model_name in ("Expense", "Income"):
        model = apps.get_model("accountants", model_name)
        for row in model.objects.select_related("month", "year"):
            fallback = row.created_at.date() if row.created_at else datetime.date.today()
            row.occurred_on = _to_date(
                getattr(row.month, "name", None), getattr(row.year, "name", None), fallback
            )
            row.save(update_fields=["occurred_on"])


def backwards(apps, schema_editor):
    """Recreate the lookup rows so the ledger can point at them again."""
    Month = apps.get_model("accountants", "Month")
    Year = apps.get_model("accountants", "Year")
    for model_name in ("Expense", "Income"):
        model = apps.get_model("accountants", model_name)
        for row in model.objects.all():
            month, _ = Month.objects.get_or_create(name=calendar.month_name[row.occurred_on.month])
            year, _ = Year.objects.get_or_create(name=str(row.occurred_on.year))
            model.objects.filter(pk=row.pk).update(month=month, year=year)


class Migration(migrations.Migration):

    dependencies = [
        ("accountants", "0003_billing_models"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="expense", name="month"),
        migrations.RemoveField(model_name="expense", name="year"),
        migrations.RemoveField(model_name="income", name="month"),
        migrations.RemoveField(model_name="income", name="year"),
        migrations.DeleteModel(name="Month"),
        migrations.DeleteModel(name="Year"),
    ]
