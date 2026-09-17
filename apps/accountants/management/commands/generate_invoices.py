"""Raise the monthly invoices. Intended for cron, safe to re-run."""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.accountants.models import BillingSettings
from apps.accountants.services import generate_invoices, refresh_overdue
from apps.core.utils import month_start


class Command(BaseCommand):
    help = "Generate this month's invoices for every billable client."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            help="Month to bill as YYYY-MM (defaults to the current month).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be billed without writing anything.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when auto-generation is switched off in billing settings.",
        )

    def handle(self, *args, **options):
        period = self._parse_period(options.get("period"))
        settings_row = BillingSettings.load()

        if not settings_row.auto_generate and not options["force"]:
            self.stdout.write(
                self.style.WARNING(
                    "Auto-generation is off in billing settings; nothing was billed. "
                    "Pass --force to override."
                )
            )
            return

        result = generate_invoices(period, dry_run=options["dry_run"])

        for invoice in result.created:
            self.stdout.write(f"  {invoice.client.client_code}  {invoice.total}")
        for code, reason in result.skipped:
            self.stdout.write(self.style.NOTICE(f"  skipped {code}: {reason}"))

        verb = "would raise" if options["dry_run"] else "raised"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {result.created_count} invoice(s) for {result.period:%B %Y}, "
                f"total {result.billed_total}."
            )
        )

        if not options["dry_run"]:
            flagged = refresh_overdue()
            if flagged:
                self.stdout.write(f"{flagged} invoice(s) moved to overdue.")

    def _parse_period(self, raw: str | None) -> date:
        if not raw:
            return month_start()
        try:
            year, month = (int(part) for part in raw.split("-")[:2])
            return date(year, month, 1)
        except (ValueError, TypeError) as exc:
            raise CommandError("--period must look like 2026-09.") from exc
