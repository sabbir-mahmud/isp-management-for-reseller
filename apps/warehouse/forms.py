from django import forms

from apps.accounts.forms import BootstrapFormMixin

from .models import Category, Onu, Product, StockMovement


class CategoryForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "description"]


class ProductForm(BootstrapFormMixin, forms.ModelForm):
    """Quantity is absent by design — stock moves through `StockMovement`."""

    opening_quantity = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        help_text="Units on hand right now (recorded as a stock receipt).",
    )

    class Meta:
        model = Product
        fields = ["name", "model", "category", "unit_price", "sku", "reorder_level", "status"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Editing must not silently re-add opening stock.
            self.fields.pop("opening_quantity")


class OnuForm(BootstrapFormMixin, forms.ModelForm):
    fieldsets = (
        {
            "title": "Device",
            "caption": "The serial on the label, and what the unit is. The serial "
            "is how it is found again when it comes back.",
            "fields": ["serial", "model", "name", "port"],
        },
        {
            "title": "Purchase",
            "caption": "What it cost and when it was bought, for the stock value "
            "and the age of the fleet.",
            "fields": ["purchase_price", "purchased_on"],
        },
        {
            "title": "Condition",
            "caption": "Whether it can go to a client. Installing and removing a "
            "unit is done from the client's record, which keeps this in step.",
            "fields": ["status", "note"],
        },
    )
    wide_fields = frozenset({"status", "note"})
    compact_fields = frozenset({"port", "purchase_price", "purchased_on"})
    field_prefixes = {"purchase_price": "৳"}

    class Meta:
        model = Onu
        fields = [
            "serial",
            "name",
            "model",
            "port",
            "purchase_price",
            "purchased_on",
            "status",
            "note",
        ]
        widgets = {
            "status": forms.RadioSelect,
            "purchased_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {
            "name": "Label",
            "port": "LAN ports",
            "purchase_price": "Cost",
            "purchased_on": "Bought on",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["serial"].widget.attrs.update(
            {"placeholder": "e.g. VSOL24A1B2C3", "autocomplete": "off", "spellcheck": "false"}
        )
        self.fields["model"].widget.attrs.setdefault("placeholder", "e.g. VSOL V2802")
        self.fields["name"].widget.attrs.setdefault("placeholder", "Optional")
        self.fields["name"].help_text = "A nickname, if the serial is not enough."
        self.fields["note"].widget.attrs.setdefault(
            "placeholder", "e.g. Returned with a bad PON port"
        )

        # Offer the models already in the fleet as suggestions, so one model
        # is not spelled three ways across the stock.
        self.fields["model"].widget.attrs["list"] = "onu-models"
        self.model_suggestions = list(
            Onu.objects.exclude(model="")
            .order_by("model")
            .values_list("model", flat=True)
            .distinct()
        )

        status = self.fields["status"]
        client = self.instance.assigned_client if self.instance.pk else None
        if client is not None:
            # Installed units change status through the client, never here:
            # editing it alone is how a device ended up "in stock" in a home.
            status.disabled = True
            status.help_text = (
                f"Installed at {client.name} ({client.client_code}). Remove it from "
                "their record to change this."
            )
        else:
            status.choices = [
                choice for choice in Onu.Status.choices if choice[0] != Onu.Status.ASSIGNED
            ]
            status.help_text = "Assigned is set by installing it on a client."


class StockMovementForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = StockMovement
        fields = ["product", "kind", "quantity", "reason", "reference", "occurred_on"]
        widgets = {"occurred_on": forms.DateInput(attrs={"type": "date"})}

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        quantity = cleaned.get("quantity")
        product = cleaned.get("product")

        if quantity is None:
            return cleaned
        if kind in {StockMovement.Kind.IN, StockMovement.Kind.OUT} and quantity <= 0:
            self.add_error("quantity", "Use a positive number; the movement type sets the sign.")
        if kind == StockMovement.Kind.OUT and product and quantity > product.quantity:
            self.add_error(
                "quantity",
                f"Only {product.quantity} in stock. Record an adjustment if the count is wrong.",
            )
        return cleaned
