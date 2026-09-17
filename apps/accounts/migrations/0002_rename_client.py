"""`Clients` -> `Client`, and field names that say what they mean.

`ip` held either an IP or a PPPoE username, so it becomes `username`;
`pop_name` was a foreign key, not a name.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("warehouse", "0002_rename_fields"),
    ]

    operations = [
        migrations.RenameModel(old_name="Clients", new_name="Client"),
        migrations.RenameField("client", old_name="ip", new_name="username"),
        migrations.RenameField("client", old_name="pop_name", new_name="pop"),
        migrations.RenameField("package", old_name="price", new_name="monthly_price"),
        migrations.RenameField("package", old_name="active", new_name="is_active"),
    ]
