import django_filters
from django import forms

from .models import Category, Onu, Product, StockMovement


class ProductFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Name, model or SKU", "class": "form-control"}
        ),
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
        fields = ["q", "category", "status"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(name__icontains=value) | Q(model__icontains=value) | Q(sku__icontains=value)
        )


class OnuFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(attrs={"placeholder": "Serial or model", "class": "form-control"}),
    )
    status = django_filters.ChoiceFilter(
        choices=Onu.Status.choices,
        empty_label="Any status",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Onu
        fields = ["q", "status"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(serial__icontains=value) | Q(model__icontains=value) | Q(name__icontains=value)
        )


class StockMovementFilter(django_filters.FilterSet):
    kind = django_filters.ChoiceFilter(
        choices=StockMovement.Kind.choices,
        empty_label="Any movement",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    occurred_on = django_filters.DateFromToRangeFilter(
        label="Between",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = StockMovement
        fields = ["kind", "occurred_on"]
