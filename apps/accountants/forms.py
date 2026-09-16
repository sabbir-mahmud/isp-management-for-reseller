from django import forms

from apps.accounts.forms import BootstrapFormMixin
from apps.core.choices import CollectionMode

from .models import BillingSettings, Expense, Income, Invoice, Payment, UpstreamSettlement


class BillingSettingsForm(BootstrapFormMixin, forms.ModelForm):
    #: What each arrangement means, for the guide under the choice.
    COLLECTION_GUIDE = {
        CollectionMode.RESELLER: "Customers pay you. You keep the commission and "
        "remit the rest upstream — the Upstream page tracks what you owe.",
        CollectionMode.UPSTREAM: "Customers pay the upstream operator online. They "
        "pay you the commission afterwards — the Upstream page tracks what they owe.",
    }
    #: The longest a bill can run before it is due. Beyond this it is a typo.
    MAX_DUE_DAYS = 90

    fieldsets = (
        {
            "title": "Collection",
            "caption": "Who takes the customer's money by default. A client can be "
            "set differently on their own record.",
            "fields": ["collection_mode", "upstream_name"],
        },
        {
            "title": "Commission",
            "caption": "Your share of every bill, unless a package or a client has its own rate.",
            "fields": ["commission_percent"],
        },
        {
            "title": "Invoices",
            "caption": "How new invoices are numbered, and how long a customer has to pay.",
            "fields": ["invoice_prefix", "due_days"],
        },
        {
            "title": "Automation",
            "caption": "Whether the scheduled job on the 1st raises the month's "
            "invoices on its own.",
            "fields": ["auto_generate"],
        },
    )
    wide_fields = frozenset({"collection_mode", "upstream_name"})
    compact_fields = frozenset({"commission_percent", "invoice_prefix", "due_days"})
    field_addons = {
        "collection_mode": "accountants/partials/settings_collection_guide.html",
        "commission_percent": "accountants/partials/settings_split_preview.html",
        "due_days": "accountants/partials/settings_invoice_preview.html",
    }

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
        widgets = {"collection_mode": forms.RadioSelect}
        labels = {
            "collection_mode": "Default arrangement",
            "upstream_name": "Upstream operator",
            "commission_percent": "Commission %",
            "invoice_prefix": "Number prefix",
            "due_days": "Days to pay",
            "auto_generate": "Raise invoices automatically each month",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collection_guide = self.COLLECTION_GUIDE
        self.fields[
            "collection_mode"
        ].help_text = "Existing invoices keep the arrangement they were raised under."
        self.fields["upstream_name"].widget.attrs.setdefault(
            "placeholder", "e.g. Link3 Technologies"
        )
        self.fields[
            "upstream_name"
        ].help_text = "Shown wherever the app says who a customer pays, and on the Upstream page."
        self.fields["commission_percent"].widget.attrs.update(
            {"min": 0, "max": 100, "step": "0.01", "inputmode": "decimal"}
        )
        self.fields["commission_percent"].help_text = "Between 0 and 100."
        self.fields["invoice_prefix"].widget.attrs.update(
            {"autocomplete": "off", "spellcheck": "false", "style": "text-transform: uppercase"}
        )
        self.fields[
            "invoice_prefix"
        ].help_text = "Letters and digits. Numbers already issued keep theirs."
        self.fields["due_days"].widget.attrs.update({"min": 0, "max": self.MAX_DUE_DAYS})
        self.fields["due_days"].help_text = "After the issue date. 0 means due the same day."
        self.fields[
            "auto_generate"
        ].help_text = (
            "Off: nothing is billed until someone uses Generate month on the Invoices page."
        )

    def clean_invoice_prefix(self):
        prefix = self.cleaned_data["invoice_prefix"].strip().upper()
        # ASCII only: the number goes on paper, in URLs and into other systems.
        if not (prefix.isascii() and prefix.isalnum()):
            raise forms.ValidationError(
                "Use the letters A–Z and digits only; the number adds its own dashes."
            )
        return prefix

    def clean_due_days(self):
        days = self.cleaned_data["due_days"]
        if days > self.MAX_DUE_DAYS:
            raise forms.ValidationError(f"Keep it to {self.MAX_DUE_DAYS} days or fewer.")
        return days

    def clean(self):
        cleaned = super().clean()
        # Every "pays upstream" sentence in the app needs a name to say.
        if (
            cleaned.get("collection_mode") == CollectionMode.UPSTREAM
            and not (cleaned.get("upstream_name") or "").strip()
        ):
            self.add_error(
                "upstream_name",
                "Name the operator customers pay, so screens can tell them who it is.",
            )
        return cleaned


class InvoiceForm(BootstrapFormMixin, forms.ModelForm):
    # The same four questions the monthly run answers on its own: whose bill,
    # which month and when it falls due, how much, and who takes the money.
    fieldsets = (
        {
            "title": "Bill to",
            "caption": "The client, and the month this bill covers. A client "
            "gets one invoice per month.",
            "fields": ["client", "period"],
        },
        {
            "title": "Dates",
            "caption": "When the bill goes out, and when it turns overdue.",
            "fields": ["issue_date", "due_date"],
        },
        {
            "title": "Amount",
            "caption": "What is charged, less any discount agreed for this month. "
            "The total and the commission are worked out on save.",
            "fields": ["subtotal", "discount"],
        },
        {
            "title": "Collection",
            "caption": "Who takes the payment, and the share of it you keep. "
            "Fixed on this invoice, whatever the settings say later.",
            "fields": ["collection_mode", "commission_percent"],
        },
        {
            "title": "Note",
            "caption": "Shown on the invoice under the charges.",
            "fields": ["note"],
        },
    )
    wide_fields = frozenset({"client", "note"})
    compact_fields = frozenset(
        {"period", "issue_date", "due_date", "subtotal", "discount", "commission_percent"}
    )

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
        labels = {
            "period": "Billing month",
            "issue_date": "Issued on",
            "due_date": "Due on",
            "subtotal": "Amount billed",
            "collection_mode": "Collected by",
            "commission_percent": "Commission %",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = self.fields["client"].queryset.order_by("name")
        self.fields["period"].help_text = "Any day in the month; it is stored as the 1st."
        self.fields["discount"].help_text = "Leave at 0 for none."
        # The section heading names it already.
        self.fields["note"].label = ""
        self.fields["note"].widget.attrs.setdefault(
            "placeholder", "e.g. Installation charged with the first month"
        )

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

    fieldsets = (
        {
            "title": "Amount",
            "caption": "What was handed over. Anything less than the balance "
            "leaves the invoice partly paid.",
            "fields": ["amount"],
        },
        {
            "title": "How it was paid",
            "caption": "The channel and its transaction ID, so the money can be "
            "matched to a statement later.",
            "fields": ["method", "reference", "received_on"],
        },
        {
            "title": "Note",
            "caption": "Anything worth knowing when this payment is looked at again.",
            "fields": ["note"],
        },
    )
    wide_fields = frozenset({"amount", "method"})
    compact_fields = frozenset({"received_on"})
    field_addons = {"amount": "accountants/partials/payment_amount_addon.html"}
    field_prefixes = {"amount": "৳"}

    class Meta:
        model = Payment
        fields = ["amount", "method", "received_on", "reference", "note"]
        widgets = {
            "method": forms.RadioSelect,
            "received_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {"received_on": "Received on", "reference": "Transaction ID / receipt no."}

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.invoice = invoice
        self.fields["note"].label = ""
        self.fields["amount"].widget.attrs.update(
            {"inputmode": "decimal", "min": "0.01", "step": "0.01", "autofocus": True}
        )
        if invoice is None:
            return

        self.fields["amount"].initial = invoice.amount_due
        self.fields["amount"].widget.attrs["max"] = str(invoice.amount_due)

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


class LedgerForm(BootstrapFormMixin, forms.ModelForm):
    """The shared shape of the expense and income forms.

    Each ledger names the choice field its entries are grouped by (`kind`),
    and the sections, tiles and prompts follow from that.
    """

    kind_field = ""
    kind_caption = ""
    description_placeholder = ""
    amount_caption = ""

    wide_fields = frozenset({"description", "category", "source", "note"})
    compact_fields = frozenset({"amount", "occurred_on"})
    field_prefixes = {"amount": "৳"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fieldsets = (
            {
                "title": "What it was",
                "caption": self.kind_caption,
                "fields": ["description", self.kind_field],
            },
            {
                "title": "Amount",
                "caption": self.amount_caption,
                "fields": ["amount", "occurred_on"],
            },
            {
                "title": "Note",
                "caption": "An invoice or receipt number, a name, anything that explains it later.",
                "fields": ["note"],
            },
        )
        self.fields["description"].widget.attrs.setdefault(
            "placeholder", self.description_placeholder
        )
        self.fields["amount"].widget.attrs.update({"inputmode": "decimal", "step": "0.01"})
        self.fields["note"].label = ""
        self.fields["note"].widget.attrs.setdefault("placeholder", "Optional")


class ExpenseForm(LedgerForm):
    kind_field = "category"
    kind_caption = "A line you will recognise on the report, and the category it is totalled under."
    description_placeholder = "e.g. September bandwidth bill"
    amount_caption = (
        "What was paid, and the day it was paid. The date decides which month's report it lands in."
    )

    class Meta:
        model = Expense
        fields = ["description", "category", "amount", "occurred_on", "note"]
        widgets = {
            "category": forms.RadioSelect,
            "occurred_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {"occurred_on": "Paid on"}


class IncomeForm(LedgerForm):
    kind_field = "source"
    kind_caption = "A line you will recognise on the report, and where the money came from."
    description_placeholder = "e.g. Installation, Karim Road"
    amount_caption = (
        "What was received, and the day it came in. The date decides which month's "
        "report it lands in."
    )

    class Meta:
        model = Income
        fields = ["description", "source", "amount", "occurred_on", "note"]
        widgets = {
            "source": forms.RadioSelect,
            "occurred_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {"occurred_on": "Received on"}


class SettlementForm(BootstrapFormMixin, forms.ModelForm):
    """Record money moving to or from the upstream operator."""

    fieldsets = (
        {
            "title": "Direction",
            "caption": "Paying upstream their share of what you collected, or "
            "receiving the commission on bills paid to them directly.",
            "fields": ["kind"],
        },
        {
            "title": "Amount",
            "caption": "What moved, and the month of payments it settles. "
            "A month can be settled in several parts.",
            "fields": ["amount", "period"],
        },
        {
            "title": "Record",
            "caption": "When it happened, and the reference that ties it to a "
            "bank or upstream statement.",
            "fields": ["settled_on", "reference", "note"],
        },
    )
    wide_fields = frozenset({"kind", "note"})
    compact_fields = frozenset({"period", "settled_on"})
    field_prefixes = {"amount": "৳"}

    class Meta:
        model = UpstreamSettlement
        fields = ["kind", "amount", "period", "settled_on", "reference", "note"]
        widgets = {
            "kind": forms.RadioSelect,
            "period": forms.DateInput(attrs={"type": "date"}),
            "settled_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "period": "For the month of",
            "settled_on": "Settled on",
            "reference": "Bank / statement reference",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A radio group of two with no blank: a model field without a default
        # would otherwise offer a "---------" tile.
        self.fields["kind"].choices = UpstreamSettlement.Kind.choices
        self.fields["period"].help_text = "Any date inside the month being settled."
        self.fields["amount"].widget.attrs.update({"inputmode": "decimal", "step": "0.01"})
        self.fields["note"].widget.attrs.setdefault("placeholder", "Optional")

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
