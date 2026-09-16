"""Flag invoices that have passed their due date. Run daily."""

from django.core.management.base import BaseCommand

from apps.accountants.services import refresh_overdue


class Command(BaseCommand):
    help = "Mark unpaid invoices past their due date as overdue."

    def handle(self, *args, **options):
        count = refresh_overdue()
        self.stdout.write(self.style.SUCCESS(f"{count} invoice(s) marked overdue."))
