from django import forms

from apps.accounts.forms import BootstrapFormMixin

from .models import BillingSettings, Expense, Income, Invoice, Payment, UpstreamSettlement


class BillingSettingsForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = BillingSettings
        fields = [
            "collection_mode",
            "upstream_name",
            "commission_percent",
            "invoice_prefix",
            "due_days",
            "auto_generate",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collection_mode"].help_text = (
            "How customers normally pay. Existing invoices keep the arrangement "
            "they were raised under; this applies to new ones."
        )


class InvoiceForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "client",
            "period",
            "issue_date",
            "due_date",
            "subtotal",
            "discount",
            "collection_mode",
            "commission_percent",
            "note",
        ]
        widgets = {
            "period": forms.DateInput(attrs={"type": "date"}),
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        issue, due = cleaned.get("issue_date"), cleaned.get("due_date")
        if issue and due and due < issue:
            self.add_error("due_date", "The due date cannot come before the issue date.")
        if cleaned.get("discount", 0) > cleaned.get("subtotal", 0):
            self.add_error("discount", "The discount cannot exceed the amount billed.")
        return cleaned


class PaymentForm(BootstrapFormMixin, forms.ModelForm):
    """Take a payment against one invoice.

    The invoice is fixed by the URL, so it is not an editable field — that
    also stops a stale form posting money onto the wrong bill.
    """

    class Meta:
        model = Payment
        fields = ["amount", "method", "received_on", "reference", "note"]
        widgets = {"received_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
        if invoice is None:
            return

        self.fields["amount"].initial = invoice.amount_due
        self.fields["amount"].help_text = f"Outstanding on this invoice: {invoice.amount_due}"

        if not invoice.collected_by_reseller:
            # The customer paid the upstream operator; this form is recording
            # that fact from their statement, not taking money over a counter.
            self.fields["method"].initial = Payment.Method.ONLINE
            self.fields["reference"].help_text = (
                "The upstream operator's transaction ID, so the payment can be "
                "traced back to their statement."
            )

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        if self.invoice is not None and amount > self.invoice.amount_due:
            raise forms.ValidationError(
                f"That is more than the {self.invoice.amount_due} still owed on this invoice."
            )
        return amount


class ExpenseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["description", "category", "amount", "occurred_on", "note"]
        widgets = {"occurred_on": forms.DateInput(attrs={"type": "date"})}


class IncomeForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Income
        fields = ["description", "source", "amount", "occurred_on", "note"]
        widgets = {"occurred_on": forms.DateInput(attrs={"type": "date"})}


class SettlementForm(BootstrapFormMixin, forms.ModelForm):
    """Record money moving to or from the upstream operator."""

    class Meta:
        model = UpstreamSettlement
        fields = ["kind", "amount", "period", "settled_on", "reference", "note"]
        widgets = {
            "period": forms.DateInput(attrs={"type": "date"}),
            "settled_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period"].help_text = "Any date inside the month being settled."

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount


class GenerateInvoicesForm(forms.Form):
    """Confirm the month before raising a batch of invoices."""

    period = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Any date inside the month you want to bill.",
    )
