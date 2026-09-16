"""Billing screens: invoices, payments and the two manual ledgers."""

from decimal import Decimal

from django.contrib import messages
from django.db.models import Case, Count, DecimalField, F, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, FormView, UpdateView

from apps.accounts.views import FilteredListView
from apps.core.aggregates import money_sum
from apps.core.choices import CollectionMode
from apps.core.mixins import CrudViewMixin, PageTitleMixin, StaffViewMixin
from apps.core.utils import month_start

from .filters import ExpenseFilter, IncomeFilter, InvoiceFilter, PaymentFilter, SettlementFilter
from .forms import (
    BillingSettingsForm,
    ExpenseForm,
    GenerateInvoicesForm,
    IncomeForm,
    InvoiceForm,
    PaymentForm,
    SettlementForm,
)
from .models import BillingSettings, Expense, Income, Invoice, Payment, UpstreamSettlement
from .services import (
    BillingError,
    cancel_invoice,
    generate_invoices,
    record_payment,
    upstream_position,
)


class InvoiceListView(FilteredListView):
    permission_required = "accountants.view_invoice"
    model = Invoice
    filterset_class = InvoiceFilter
    template_name = "accountants/invoice_list.html"
    htmx_template_name = "accountants/partials/invoice_rows.html"
    context_object_name = "invoices"
    page_title = "Invoices"
    page_subtitle = "What was billed, and what is still owed"

    def get_queryset(self):
        self.filterset = self.filterset_class(
            self.request.GET, queryset=Invoice.objects.with_related()
        )
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = self.filterset.qs.aggregate(
            count=Count("pk"),
            billed=money_sum("total"),
            paid=money_sum("amount_paid"),
            commission=money_sum("commission_amount"),
        )
        rows["due"] = rows["billed"] - rows["paid"]
        context["totals"] = rows
        return context


class InvoiceDetailView(StaffViewMixin, PageTitleMixin, DetailView):
    permission_required = "accountants.view_invoice"
    model = Invoice
    template_name = "accountants/invoice_detail.html"
    context_object_name = "invoice"

    def get_queryset(self):
        return Invoice.objects.with_related().prefetch_related("lines", "payments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = self.object.number
        context["page_subtitle"] = f"{self.object.client.name} · {self.object.period:%B %Y}"
        context["payment_form"] = PaymentForm(invoice=self.object)
        return context


class InvoiceCreateView(CrudViewMixin, CreateView):
    permission_required = "accountants.add_invoice"
    model = Invoice
    form_class = InvoiceForm
    template_name = "form.html"
    success_message = "Invoice created."
    page_title = "New invoice"


class InvoiceUpdateView(CrudViewMixin, UpdateView):
    permission_required = "accountants.change_invoice"
    model = Invoice
    form_class = InvoiceForm
    template_name = "form.html"
    success_message = "Invoice updated."
    page_title = "Edit invoice"

    def form_valid(self, form):
        response = super().form_valid(form)
        self.object.recalculate()
        return response


class InvoiceCancelView(StaffViewMixin, DetailView):
    permission_required = "accountants.change_invoice"
    model = Invoice
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        invoice = self.get_object()
        try:
            cancel_invoice(invoice, actor=request.user)
            messages.success(request, f"{invoice.number} was cancelled.")
        except BillingError as exc:
            messages.error(request, str(exc))
        return redirect("invoice_detail", pk=invoice.pk)


class GenerateInvoicesView(StaffViewMixin, PageTitleMixin, FormView):
    """Raise the whole month's invoices from the UI.

    Shows a dry run first — an operator should see what a batch will do
    before it writes a few hundred rows.
    """

    permission_required = "accountants.add_invoice"
    form_class = GenerateInvoicesForm
    template_name = "accountants/generate_invoices.html"
    page_title = "Generate monthly invoices"

    def get_initial(self):
        return {"period": month_start()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        period = self.request.GET.get("period")
        preview_period = month_start(_parse_date(period)) if period else month_start()
        context["preview"] = generate_invoices(preview_period, dry_run=True)
        context["preview_period"] = preview_period
        return context

    def form_valid(self, form):
        result = generate_invoices(form.cleaned_data["period"], actor=self.request.user)
        if result.created_count:
            messages.success(
                self.request,
                f"{result.created_count} invoice(s) raised for {result.period:%B %Y}, "
                f"totalling {result.billed_total}.",
            )
        else:
            messages.info(self.request, f"Nothing to bill for {result.period:%B %Y}.")
        return redirect(f"{reverse('invoice_list')}?period={result.period:%Y-%m-%d}")


def _parse_date(value):
    from datetime import date

    try:
        parts = [int(p) for p in value.split("-")]
        return date(parts[0], parts[1], parts[2] if len(parts) > 2 else 1)
    except ValueError, IndexError, AttributeError:
        return None


# ---------------------------------------------------------------------------#
# Payments
# ---------------------------------------------------------------------------#


class PaymentListView(FilteredListView):
    permission_required = "accountants.view_payment"
    model = Payment
    filterset_class = PaymentFilter
    template_name = "accountants/payment_list.html"
    context_object_name = "payments"
    page_title = "Payments"
    page_subtitle = "Cash actually received"

    def get_queryset(self):
        queryset = Payment.objects.select_related("client", "invoice", "created_by")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # The keys deliberately avoid the column names they sum: an alias that
        # shadows a field makes the `F("amount")` below resolve to the other
        # aggregate, and Django refuses with "'amount' is an aggregate".
        context["totals"] = self.filterset.qs.aggregate(
            count=Count("pk"),
            gross=money_sum("amount"),
            commission=money_sum("commission_amount"),
            reseller_cash=money_sum(
                Case(
                    When(collection_mode=CollectionMode.RESELLER, then=F("amount")),
                    default=Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
        )
        return context


class PaymentCreateView(StaffViewMixin, PageTitleMixin, FormView):
    """Record a payment against the invoice named in the URL."""

    permission_required = "accountants.add_payment"
    form_class = PaymentForm
    template_name = "form.html"
    page_title = "Record payment"

    @property
    def invoice(self):
        if not hasattr(self, "_invoice"):
            self._invoice = get_object_or_404(Invoice, pk=self.kwargs["pk"])
        return self._invoice

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["invoice"] = self.invoice
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_subtitle"] = (
            f"{self.invoice.number} · {self.invoice.client.name} · "
            f"{self.invoice.amount_due} outstanding"
        )
        # Not a `CrudViewMixin` view, so it names its own way back.
        context["cancel_url"] = self.invoice.get_absolute_url()
        return context

    def form_valid(self, form):
        try:
            record_payment(
                self.invoice,
                form.cleaned_data["amount"],
                method=form.cleaned_data["method"],
                received_on=form.cleaned_data["received_on"],
                reference=form.cleaned_data.get("reference", ""),
                actor=self.request.user,
            )
        except BillingError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)
        messages.success(self.request, "Payment recorded.")
        return redirect("invoice_detail", pk=self.invoice.pk)


class PaymentDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "accountants.delete_payment"
    model = Payment
    template_name = "confirm_delete.html"
    page_title = "Reverse payment"

    def get_success_url(self):
        return reverse("invoice_detail", args=[self.object.invoice_id])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["warning"] = "Reversing a payment puts the amount back on the invoice."
        return context


# ---------------------------------------------------------------------------#
# Upstream settlement
# ---------------------------------------------------------------------------#


class SettlementListView(FilteredListView):
    """The running position with the upstream operator, and how it got there."""

    permission_required = "accountants.view_upstreamsettlement"
    model = UpstreamSettlement
    filterset_class = SettlementFilter
    template_name = "accountants/settlement_list.html"
    context_object_name = "settlements"
    page_title = "Upstream"
    page_subtitle = "What you owe them, and what they owe you"

    def get_queryset(self):
        queryset = UpstreamSettlement.objects.select_related("created_by")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        settings_row = BillingSettings.load()
        context["settings_row"] = settings_row
        context["upstream_name"] = settings_row.upstream_name or "Upstream operator"
        # All-time is the number that answers "are we square"; the month view
        # is for reconciling a single statement.
        context["position"] = upstream_position()
        context["month_position"] = upstream_position(month_start())
        context["this_month"] = month_start()
        return context


class SettlementCreateView(CrudViewMixin, CreateView):
    permission_required = "accountants.add_upstreamsettlement"
    model = UpstreamSettlement
    form_class = SettlementForm
    template_name = "form.html"
    success_url = reverse_lazy("settlement_list")
    success_message = "Settlement recorded."
    page_title = "Record settlement"

    def get_initial(self):
        return {"period": month_start(), "kind": self.request.GET.get("kind") or None}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notice"] = (
            "A remittance to the upstream operator is not an expense — that share was "
            "never your revenue, so recording it in both places would deduct it twice."
        )
        return context


class SettlementDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "accountants.delete_upstreamsettlement"
    model = UpstreamSettlement
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("settlement_list")
    page_title = "Delete settlement"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["warning"] = (
            "Removing this settlement changes your position with the upstream operator."
        )
        return context


# ---------------------------------------------------------------------------#
# Ledgers
# ---------------------------------------------------------------------------#


class ExpenseListView(FilteredListView):
    permission_required = "accountants.view_expense"
    model = Expense
    filterset_class = ExpenseFilter
    template_name = "accountants/expense_list.html"
    context_object_name = "expenses"
    page_title = "Expenses"
    page_subtitle = "Money out: bandwidth, salaries, hardware"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totals"] = self.filterset.qs.aggregate(
            count=Count("pk"), amount=money_sum("amount")
        )
        return context


class ExpenseCreateView(CrudViewMixin, CreateView):
    permission_required = "accountants.add_expense"
    model = Expense
    form_class = ExpenseForm
    template_name = "form.html"
    success_url = reverse_lazy("expense_list")
    success_message = "Expense recorded."
    page_title = "Add expense"


class ExpenseUpdateView(CrudViewMixin, UpdateView):
    permission_required = "accountants.change_expense"
    model = Expense
    form_class = ExpenseForm
    template_name = "form.html"
    success_url = reverse_lazy("expense_list")
    success_message = "Expense updated."
    page_title = "Edit expense"


class ExpenseDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "accountants.delete_expense"
    model = Expense
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("expense_list")
    page_title = "Delete expense"


class IncomeListView(FilteredListView):
    permission_required = "accountants.view_income"
    model = Income
    filterset_class = IncomeFilter
    template_name = "accountants/income_list.html"
    context_object_name = "incomes"
    page_title = "Other income"
    page_subtitle = "Installations, hardware sales, repairs — not subscriptions"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totals"] = self.filterset.qs.aggregate(
            count=Count("pk"), amount=money_sum("amount")
        )
        return context


class IncomeCreateView(CrudViewMixin, CreateView):
    permission_required = "accountants.add_income"
    model = Income
    form_class = IncomeForm
    template_name = "form.html"
    success_url = reverse_lazy("income_list")
    success_message = "Income recorded."
    page_title = "Add income"


class IncomeUpdateView(CrudViewMixin, UpdateView):
    permission_required = "accountants.change_income"
    model = Income
    form_class = IncomeForm
    template_name = "form.html"
    success_url = reverse_lazy("income_list")
    success_message = "Income updated."
    page_title = "Edit income"


class IncomeDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "accountants.delete_income"
    model = Income
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("income_list")
    page_title = "Delete income"


# ---------------------------------------------------------------------------#
# Settings
# ---------------------------------------------------------------------------#


class BillingSettingsView(CrudViewMixin, UpdateView):
    permission_required = "accountants.change_billingsettings"
    model = BillingSettings
    form_class = BillingSettingsForm
    template_name = "form.html"
    success_url = reverse_lazy("dashboard")
    success_message = "Billing settings saved."
    page_title = "Billing settings"
    page_subtitle = "Commission split, invoice numbering and due dates"

    def get_object(self, queryset=None):
        return BillingSettings.load()
