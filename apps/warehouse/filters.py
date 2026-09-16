import django_filters
from django import forms
from django.db.models import F, Q

from apps.core.utils import date_window

from .models import Category, Onu, Product, StockMovement


class ProductFilter(django_filters.FilterSet):
    #: Stock levels, shared with the chips on the stock page.
    LEVEL_CHOICES = [
        ("healthy", "Healthy"),
        ("low", "Running low"),
        ("out", "Out of stock"),
    ]

    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Search stock by name, model or SKU", "class": "form-control"}
        ),
    )
    level = django_filters.ChoiceFilter(
        choices=LEVEL_CHOICES,
        label="Stock level",
        empty_label="Any level",
        method="by_level",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    category = django_filters.ModelChoiceFilter(
        queryset=Category.objects.all(),
        empty_label="Any category",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    status = django_filters.ChoiceFilter(
        choices=Product.Status.choices,
        empty_label="Any status",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Product
        fields = ["q", "level", "category", "status"]

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(model__icontains=value) | Q(sku__icontains=value)
        )

    @staticmethod
    def level_q(level):
        """The condition for a stock level; `None` for an unknown one.

        Out means nothing to hand out. Low is some left, but at or under the
        reorder level. Healthy is above it.
        """
        return {
            "out": Q(quantity__lte=0),
            "low": Q(quantity__gt=0, quantity__lte=F("reorder_level")),
            "healthy": Q(quantity__gt=F("reorder_level")) & Q(quantity__gt=0),
        }.get(level)

    def by_level(self, queryset, name, value):
        match = self.level_q(value)
        return queryset.filter(match) if match is not None else queryset


def onu_model_choices():
    """The models actually in the fleet, for the ONU filter's select."""
    models = (
        Onu.objects.exclude(model="").order_by("model").values_list("model", flat=True).distinct()
    )
    return [(model, model) for model in models]


class OnuFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search ONUs by serial, model or the client they are with",
                "class": "form-control",
            }
        ),
    )
    status = django_filters.ChoiceFilter(
        choices=Onu.Status.choices,
        empty_label="Any status",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    model = django_filters.ChoiceFilter(
        # Filled per request in `__init__`, so a model bought yesterday is
        # offered today. django-filter's choice field cannot take a callable.
        choices=[],
        label="Model",
        empty_label="Any model",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    purchased_on = django_filters.DateFromToRangeFilter(
        label="Bought",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = Onu
        fields = ["q", "status", "model", "purchased_on"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.filters["model"].extra["choices"] = onu_model_choices()

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(serial__icontains=value)
            | Q(model__icontains=value)
            | Q(name__icontains=value)
            | Q(client__name__icontains=value)
            | Q(client__client_code__icontains=value)
        )


class StockMovementFilter(django_filters.FilterSet):
    WHEN_CHOICES = [
        ("7d", "Last 7 days"),
        ("month", "This month"),
        ("last_month", "Last month"),
        ("3m", "Last 3 months"),
    ]
    #: Choosing Custom in `when` reveals the `occurred_on` range in the toolbar.
    custom_range = ("when", "occurred_on")

    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search by item, reason or reference",
                "class": "form-control",
            }
        ),
    )
    kind = django_filters.ChoiceFilter(
        choices=StockMovement.Kind.choices,
        label="Type",
        empty_label="Any movement",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    product = django_filters.ModelChoiceFilter(
        queryset=Product.objects.order_by("name"),
        label="Item",
        empty_label="Any item",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    when = django_filters.ChoiceFilter(
        choices=[*WHEN_CHOICES, ("custom", "Custom dates…")],
        label="Period",
        empty_label="Any time",
        method="by_when",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    occurred_on = django_filters.DateFromToRangeFilter(
        label="Dates",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = StockMovement
        fields = ["q", "kind", "product", "when", "occurred_on"]

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(product__name__icontains=value)
            | Q(product__sku__icontains=value)
            | Q(reason__icontains=value)
            | Q(reference__icontains=value)
        )

    def by_when(self, queryset, name, value):
        bounds = date_window(value)
        return queryset.filter(occurred_on__range=bounds) if bounds else queryset
