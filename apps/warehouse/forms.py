from django import forms

from apps.accounts.forms import BootstrapFormMixin

from .models import Category, Onu, Product, StockMovement


class CategoryForm(BootstrapFormMixin, forms.ModelForm):
    fieldsets = (
        {
            "title": "Name",
            "caption": "Short and plural, the way it reads on the stock page's "
            "filter: Networking, Power, Tools.",
            "fields": ["name"],
        },
        {
            "title": "Description",
            "caption": "What belongs here, so the next person adding an item puts "
            "it in the right place.",
            "fields": ["description"],
        },
    )
    wide_fields = frozenset({"name", "description"})
    field_addons = {
        "name": "warehouse/partials/category_name_addon.html",
        "description": "warehouse/partials/category_preview_addon.html",
    }

    class Meta:
        model = Category
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        name = self.fields["name"]
        name.label = ""
        name.widget.attrs.update(
            {"placeholder": "e.g. Networking", "autocomplete": "off", "autofocus": True}
        )
        description = self.fields["description"]
        description.label = ""
        description.widget.attrs.update(
            {
                "placeholder": "e.g. Patch cords, drop wire, connectors and splitters",
                "maxlength": Category._meta.get_field("description").max_length,
            }
        )
        # Every other category's name, for the duplicate hint beside the input.
        others = Category.objects.order_by("name")
        if self.instance.pk:
            others = others.exclude(pk=self.instance.pk)
        self.other_names = list(others.values_list("name", flat=True))

    def clean_name(self):
        """Refuse a name that differs from an existing one only in case.

        The unique constraint already stops an exact repeat; "networking"
        beside "Networking" would get past it and split one shelf in two.
        """
        name = " ".join(self.cleaned_data["name"].split())
        clash = Category.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).first()
        if clash is not None:
            raise forms.ValidationError(f"{clash.name} already exists.")
        return name


class ProductForm(BootstrapFormMixin, forms.ModelForm):
    """Quantity is absent by design — stock moves through `StockMovement`."""

    opening_quantity = forms.IntegerField(
        min_value=0,
        required=False,
        initial=0,
        label="Units on hand now",
        help_text="Recorded as a stock receipt, so the count has a history from day one.",
    )

    fieldsets = (
        {
            "title": "Item",
            "caption": "What it is, and where it sits on the stock page.",
            "fields": ["name", "model", "category", "sku"],
        },
        {
            "title": "Stock",
            "caption": "What one unit costs, and the count at which it should be "
            "reordered. The stock page flags it from there.",
            "fields": ["unit_price", "reorder_level", "opening_quantity"],
        },
        {
            "title": "Availability",
            "caption": "Reserved keeps it out of everyday use; retired stops it "
            "being counted as needing a reorder.",
            "fields": ["status"],
        },
    )
    wide_fields = frozenset({"status"})
    compact_fields = frozenset({"unit_price", "reorder_level", "opening_quantity"})
    field_prefixes = {"unit_price": "৳"}

    class Meta:
        model = Product
        fields = ["name", "model", "category", "unit_price", "sku", "reorder_level", "status"]
        widgets = {"status": forms.RadioSelect}
        labels = {"sku": "SKU / serial", "reorder_level": "Reorder at"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Editing must not silently re-add opening stock.
            self.fields.pop("opening_quantity")
        self.fields["name"].widget.attrs.setdefault("placeholder", "e.g. Drop wire (100m)")
        self.fields["model"].widget.attrs.setdefault("placeholder", "Optional")
        self.fields["sku"].widget.attrs.setdefault("placeholder", "Optional")
        self.fields["reorder_level"].widget.attrs.setdefault("min", 0)


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
    fieldsets = (
        {
            "title": "Movement",
            "caption": "The item, and which way it moved. An adjustment corrects "
            "the count after a stock-take.",
            "fields": ["product", "kind"],
        },
        {
            "title": "Quantity",
            "caption": "How many units, and when. The preview shows the count "
            "this leaves on the shelf.",
            "fields": ["quantity", "occurred_on"],
        },
        {
            "title": "Why",
            "caption": "The reason and a reference — a client, a supplier invoice, "
            "a job number — so the count can be explained later.",
            "fields": ["reason", "reference"],
        },
    )
    wide_fields = frozenset({"product", "kind"})
    compact_fields = frozenset({"quantity", "occurred_on"})
    field_addons = {"quantity": "warehouse/partials/movement_quantity_addon.html"}

    class Meta:
        model = StockMovement
        fields = ["product", "kind", "quantity", "reason", "reference", "occurred_on"]
        widgets = {
            "kind": forms.RadioSelect,
            "occurred_on": forms.DateInput(attrs={"type": "date"}),
        }
        labels = {"occurred_on": "Date", "product": "Item"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A radio group with no blank "---------" tile.
        self.fields["kind"].choices = StockMovement.Kind.choices
        self.fields["product"].queryset = Product.objects.exclude(
            status=Product.Status.RETIRED
        ).order_by("name")
        self.fields["product"].label_from_instance = lambda product: (
            f"{product.name} — {product.quantity} on hand"
        )
        self.fields["quantity"].widget.attrs.update({"step": 1, "inputmode": "numeric"})
        self.fields[
            "quantity"
        ].help_text = "Positive for received and issued. For an adjustment, negative removes units."
        self.fields["reason"].widget.attrs.setdefault("placeholder", "e.g. Installed at C-000123")
        self.fields["reference"].widget.attrs.setdefault("placeholder", "Optional")

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
        if kind == StockMovement.Kind.ADJUST:
            if quantity == 0:
                self.add_error("quantity", "An adjustment of zero changes nothing.")
            elif product and product.quantity + quantity < 0:
                self.add_error(
                    "quantity",
                    f"That takes the count below zero; there are {product.quantity} on hand.",
                )
        return cleaned
