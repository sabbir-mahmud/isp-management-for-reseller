from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    # The label stays `accounts` so the existing migration history and table
    # names keep working; the domain it models is customers.
    verbose_name = "Customers"
