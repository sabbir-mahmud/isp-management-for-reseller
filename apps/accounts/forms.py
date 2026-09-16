from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.core.choices import CollectionMode
from apps.warehouse.models import Onu, Pop

from .models import Client, Package, Subscription


class BootstrapFormMixin:
    """Apply Bootstrap classes once, instead of in every template.

    Also carries the optional layout declaration that `{% form_sections %}`
    reads. A form that says nothing renders exactly as it always did: one
    labelled field after another. Declaring `fieldsets` opts it into the
    sectioned two-column layout instead.
    """

    #: Sections, as `{"title", "caption", "fields"}`. Empty means one plain stack.
    fieldsets: tuple[dict, ...] = ()
    #: Fields that need the full width of the grid (an address, a long note).
    wide_fields: frozenset[str] = frozenset()
    #: Fields holding a handful of characters, given an input to match.
    compact_fields: frozenset[str] = frozenset()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
            if isinstance(widget, forms.DateInput):
                widget.input_type = "date"


class PackageForm(BootstrapFormMixin, forms.ModelForm):
    fieldsets = (
        {
            "title": "Plan",
            "caption": "What you call it, and the line a client sees beside the name.",
            "fields": ["name", "description"],
        },
        {
            "title": "Bandwidth",
            "caption": "The speed you sell, and how much of it is cached traffic "
            "rather than upstream you pay for.",
            "fields": ["bandwidth_mbps", "ggc_mbps", "fna_mbps"],
        },
        {
            "title": "Price",
            "caption": "The list price for the plan. A client can still be put on a "
            "price agreed with them instead.",
            "fields": ["monthly_price", "commission_percent"],
        },
        {
            "title": "Availability",
            "caption": "Retiring a plan stops it being offered to new clients. "
            "Anyone already on it stays on it.",
            "fields": ["is_active"],
        },
    )
    wide_fields = frozenset({"description"})
    compact_fields = frozenset(
        {"bandwidth_mbps", "ggc_mbps", "fna_mbps", "monthly_price", "commission_percent"}
    )

    class Meta:
        model = Package
        fields = [
            "name",
            "bandwidth_mbps",
            "ggc_mbps",
            "fna_mbps",
            "monthly_price",
            "commission_percent",
            "description",
            "is_active",
        ]
        # Presentation only, so the labels read like the column headings on the
        # list rather than like field names. Changing the model's verbose names
        # would mean a migration for a piece of wording.
        labels = {
            "bandwidth_mbps": "Speed (Mbps)",
            "commission_percent": "Commission %",
            "description": "Description",
            "is_active": "On sale",
        }


class PopForm(BootstrapFormMixin, forms.ModelForm):
    fieldsets = (
        {
            "title": "Identity",
            "caption": "What this POP is called, the short code that stands in for "
            "it on reports, and where the equipment sits.",
            "fields": ["name", "code", "address"],
        },
        {
            "title": "Network",
            "caption": "Which POP feeds this one, and whether it is in service. "
            "Leave the upstream blank for a POP fed directly.",
            "fields": ["parent", "is_active"],
        },
    )
    wide_fields = frozenset({"address"})
    compact_fields = frozenset({"code"})

    class Meta:
        model = Pop
        fields = ["name", "code", "address", "parent", "is_active"]
        labels = {"is_active": "In service"}

    def clean_parent(self):
        parent = self.cleaned_data.get("parent")
        if parent and self.instance.pk and parent.pk == self.instance.pk:
            raise ValidationError("A POP cannot be its own upstream.")
        return parent


class ClientForm(BootstrapFormMixin, forms.ModelForm):
    """Client details plus the current plan, as a single form.

    The subscription is a separate table for price history, but an operator
    signing someone up should not have to fill in two screens; the view's
    `form_valid` turns these extra fields into the subscription.
    """

    package = forms.ModelChoiceField(
        queryset=Package.objects.active(), help_text="The plan this client is on."
    )
    monthly_price = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="Leave blank to charge the package's list price.",
    )
    discount = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False, initial=0, min_value=0
    )
    commission_percent = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        min_value=0,
        max_value=100,
        label="Commission %",
        help_text="Leave blank to use the package's rate, or the one in billing settings.",
    )

    # Seventeen fields in one column is a scroll, not a form. Grouped, it is
    # four short questions: who they are, where the line goes, what they pay,
    # and when you invoice them.
    fieldsets = (
        {
            "title": "Identity",
            "caption": "Who they are, and how you reach them.",
            "fields": ["name", "username", "phone", "email", "nid"],
        },
        {
            "title": "Connection",
            "caption": "Where the line lands, and the hardware on the end of it.",
            "fields": ["address", "pop", "onu", "connection_date", "status"],
        },
        {
            "title": "Plan & price",
            "caption": "The package, and what this client actually pays for it. "
            "The price and commission are agreed per client; leave them blank "
            "to follow the package.",
            "fields": ["package", "monthly_price", "discount", "commission_percent"],
        },
        {
            "title": "Billing",
            "caption": "When the invoice goes out, and who collects it.",
            "fields": ["billing_day", "collection_mode"],
        },
        {
            "title": "Notes",
            "caption": "Anything the next person answering the phone should know.",
            "fields": ["notes"],
        },
    )
    wide_fields = frozenset({"address"})
    compact_fields = frozenset(
        {"monthly_price", "discount", "commission_percent", "billing_day", "connection_date"}
    )

    class Meta:
        model = Client
        fields = [
            "name",
            "username",
            "phone",
            "email",
            "nid",
            "address",
            "pop",
            "onu",
            "status",
            "collection_mode",
            "connection_date",
            "billing_day",
            "notes",
        ]
        widgets = {
            "connection_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pop"].queryset = Pop.objects.filter(is_active=True)
        # Free ONUs, plus whichever one this client already holds — otherwise
        # editing a client would silently blank their assigned device.
        available = Q(status=Onu.Status.IN_STOCK)
        if self.instance.pk and self.instance.onu_id:
            available |= Q(pk=self.instance.onu_id)
        self.fields["onu"].queryset = Onu.objects.filter(available)
        self.fields["onu"].required = False

        # An explicit blank label, so "no override" reads as a real choice
        # rather than an empty box someone forgot to fill in.
        self.fields["collection_mode"].widget.choices = [
            ("", "Use the billing-settings default"),
            *CollectionMode.choices,
        ]

        # The "Notes" section heading names this field already.
        self.fields["notes"].label = ""

        subscription = self.instance.subscription if self.instance.pk else None
        if subscription:
            self.fields["package"].initial = subscription.package_id
            self.fields["monthly_price"].initial = subscription.monthly_price
            self.fields["discount"].initial = subscription.discount
            self.fields["commission_percent"].initial = subscription.commission_percent

    def clean_billing_day(self):
        day = self.cleaned_data["billing_day"]
        if not 1 <= day <= 28:
            raise ValidationError("Pick a day between 1 and 28 so every month can bill.")
        return day

    def clean(self):
        cleaned = super().clean()
        package = cleaned.get("package")
        if package and cleaned.get("monthly_price") in (None, ""):
            cleaned["monthly_price"] = package.monthly_price
        if cleaned.get("discount") in (None, ""):
            cleaned["discount"] = 0
        price = cleaned.get("monthly_price") or 0
        if cleaned.get("discount") and cleaned["discount"] > price:
            self.add_error("discount", "The discount cannot exceed the monthly price.")
        return cleaned


class SubscriptionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Subscription
        fields = ["package", "monthly_price", "discount", "start_date", "end_date", "status"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }
