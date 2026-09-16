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
        widgets = {"purchased_on": forms.DateInput(attrs={"type": "date"})}


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
