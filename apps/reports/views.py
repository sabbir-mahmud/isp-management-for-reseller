"""The dashboard, the monthly P&L, and CSV exports."""

import csv
from datetime import date

from django.http import HttpResponse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accountants.models import Expense, Invoice, Payment
from apps.accountants.services import upstream_position
from apps.accounts.models import Client
from apps.core.mixins import PageTitleMixin, StaffViewMixin
from apps.core.utils import add_months, month_start

from . import metrics


def _period_from_request(request) -> date:
    """Read `?period=YYYY-MM-DD` (or `YYYY-MM`), falling back to this month."""
    raw = request.GET.get("period")
    if not raw:
        return month_start()
    parts = raw.split("-")
    try:
        return month_start(date(int(parts[0]), int(parts[1]), 1))
    except ValueError, IndexError:
        return month_start()


class DashboardView(StaffViewMixin, PageTitleMixin, TemplateView):
    permission_required = "accountants.view_dashboard"
    template_name = "reports/dashboard.html"
    page_title = "Dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = _period_from_request(self.request)
        context.update(metrics.dashboard(period))
        context["page_subtitle"] = f"{period:%B %Y}"
        context["period_options"] = [add_months(month_start(), -offset) for offset in range(12)]

        # Presentation of the headline figure: what the hero number is made of,
        # and the two series the trend chart plots on its single shared axis.
        context["revenue_breakdown"] = [
            {"label": "Commission", "value": context["profit"]["commission"]},
            {"label": "Other income", "value": context["profit"]["other_income"]},
        ]
        context["revenue_series"] = [("revenue", "Revenue earned"), ("expenses", "Expenses")]
        return context


class FinancialReportView(StaffViewMixin, PageTitleMixin, TemplateView):
    """Month-by-month profit and loss, with the settlement position spelled out."""

    permission_required = "accountants.view_financial_report"
    template_name = "reports/financial.html"
    page_title = "Financial report"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = _period_from_request(self.request)
        # One scope for the whole page: the statement, the tiles and the chart
        # all want the same handful of figures, and without it each asks the
        # database again.
        with metrics.figures_scope():
            return self._assemble(context, period)

    def _assemble(self, context, period):
        prior = add_months(period, -1)
        trend = metrics.revenue_trend(12, period)

        context["period"] = period
        context["prior"] = prior
        context["page_subtitle"] = f"{period:%B %Y}"

        # Month-to-month stepping, so reading back through the year does not
        # mean going via the dropdown every time. Capped at the current month:
        # there is nothing to report from the future.
        context["previous_period"] = prior
        following = add_months(period, 1)
        context["next_period"] = following if following <= month_start() else None
        context["period_options"] = [add_months(month_start(), -offset) for offset in range(12)]

        context["statement"] = metrics.profit_and_loss(period)
        context["expense_breakdown"] = metrics.expense_breakdown(period)
        context["trend"] = trend
        context["revenue_series"] = [("revenue", "Revenue earned"), ("expenses", "Expenses")]

        # Headline tiles, each carrying the month before so the figures read as
        # movement rather than as isolated numbers.
        context["net"] = metrics.Money(
            metrics.revenue(period) - metrics.expenses(period),
            metrics.revenue(prior) - metrics.expenses(prior),
        )
        context["revenue"] = metrics.Money(metrics.revenue(period), metrics.revenue(prior))
        context["expenses"] = metrics.Money(metrics.expenses(period), metrics.expenses(prior))
        context["commission_earned"] = metrics.Money(
            metrics.commission_earned(period), metrics.commission_earned(prior)
        )
        context["billed"] = metrics.billed(period)
        context["client_payments"] = metrics.client_payments(period)
        context["collection_rate"] = metrics.collection_rate(period)
        context["outstanding"] = metrics.outstanding_total()
        context["outstanding_by_mode"] = metrics.outstanding_by_mode()
        context["aging"] = metrics.aging_buckets()
        context["commission"] = metrics.commission_split(period)
        context["upstream"] = upstream_position(period)
        context["upstream_all_time"] = upstream_position()
        return context


class ExportView(StaffViewMixin, TemplateView):
    """Stream a CSV of one dataset.

    Export is a permission of its own: the data leaves the building in a file
    anyone can forward, which is a different risk from reading it on screen.
    """

    permission_required = "accountants.export_data"

    DATASETS = {"clients", "invoices", "payments", "expenses"}

    def get(self, request, dataset, *args, **kwargs):
        if dataset not in self.DATASETS:
            return HttpResponse("Unknown dataset.", status=404)

        stamp = timezone.localdate().isoformat()
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{dataset}-{stamp}.csv"'
        writer = csv.writer(response)
        getattr(self, f"_{dataset}")(writer)
        return response

    def _clients(self, writer):
        writer.writerow(
            [
                "Code",
                "Name",
                "Username/IP",
                "Phone",
                "POP",
                "Package",
                "Monthly",
                "Status",
                "Joined",
            ]
        )
        for client in Client.objects.with_related().order_by("client_code"):
            writer.writerow(
                [
                    client.client_code,
                    client.name,
                    client.username,
                    client.phone,
                    client.pop.name if client.pop else "",
                    client.package.name if client.package else "",
                    client.monthly_price or 0,
                    client.effective_collection_mode,
                    client.get_status_display(),
                    client.connection_date,
                ]
            )

    def _invoices(self, writer):
        writer.writerow(
            [
                "Number",
                "Client",
                "Period",
                "Issued",
                "Due",
                "Total",
                "Paid",
                "Outstanding",
                "Status",
            ]
        )
        for invoice in Invoice.objects.with_related().order_by("-period", "number"):
            writer.writerow(
                [
                    invoice.number,
                    invoice.client.name,
                    f"{invoice.period:%Y-%m}",
                    invoice.issue_date,
                    invoice.due_date,
                    invoice.total,
                    invoice.amount_paid,
                    invoice.amount_due,
                    invoice.get_collection_mode_display(),
                    invoice.commission_percent,
                    invoice.commission_amount,
                    invoice.upstream_amount,
                    invoice.get_status_display(),
                ]
            )

    def _payments(self, writer):
        writer.writerow(
            [
                "Date",
                "Client",
                "Invoice",
                "Amount",
                "Commission",
                "Upstream share",
                "Collected by",
                "Method",
                "Reference",
                "Recorded by",
            ]
        )
        for payment in Payment.objects.select_related("client", "invoice", "created_by"):
            writer.writerow(
                [
                    payment.received_on,
                    payment.client.name,
                    payment.invoice.number,
                    payment.amount,
                    payment.commission_amount,
                    payment.upstream_amount,
                    payment.get_collection_mode_display(),
                    payment.get_method_display(),
                    payment.reference,
                    payment.created_by.get_username() if payment.created_by else "",
                ]
            )

    def _expenses(self, writer):
        writer.writerow(["Date", "Category", "Description", "Amount", "Note"])
        for expense in Expense.objects.all():
            writer.writerow(
                [
                    expense.occurred_on,
                    expense.get_category_display(),
                    expense.description,
                    expense.amount,
                    expense.note,
                ]
            )
