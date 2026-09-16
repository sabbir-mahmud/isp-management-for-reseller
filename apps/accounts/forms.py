from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from apps.core.choices import CollectionMode
from apps.warehouse.models import Onu, Pop

from .models import Client, Package, Subscription


class BootstrapFormMixin:
    """Apply Bootstrap classes once, instead of in every template."""

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


class PopForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Pop
        fields = ["name", "code", "address", "parent", "is_active"]

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
            "notes": forms.Textarea(attrs={"rows": 2}),
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
