import django_filters
from django import forms

from apps.core.choices import CollectionMode

from .models import Expense, Income, Invoice, Payment, UpstreamSettlement


class InvoiceFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Invoice no. or client", "class": "form-control"}
        ),
    )
    status = django_filters.ChoiceFilter(
        choices=Invoice.Status.choices,
        empty_label="Any status",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    collection_mode = django_filters.ChoiceFilter(
        choices=CollectionMode.choices,
        label="Collected by",
        empty_label="Either",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    period = django_filters.DateFilter(
        field_name="period",
        lookup_expr="exact",
        label="Month",
        widget=forms.DateInput(attrs={"type": "month", "class": "form-control"}),
        method="by_month",
    )

    class Meta:
        model = Invoice
        fields = ["q", "status", "collection_mode", "period"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(number__icontains=value)
            | Q(client__name__icontains=value)
            | Q(client__client_code__icontains=value)
        )

    def by_month(self, queryset, name, value):
        """`<input type="month">` posts YYYY-MM-01, which is already the period."""
        return queryset.filter(period=value.replace(day=1))


class PaymentFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Client, invoice or reference", "class": "form-control"}
        ),
    )
    method = django_filters.ChoiceFilter(
        choices=Payment.Method.choices,
        empty_label="Any method",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    collection_mode = django_filters.ChoiceFilter(
        choices=CollectionMode.choices,
        label="Collected by",
        empty_label="Either",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    received_on = django_filters.DateFromToRangeFilter(
        label="Received between",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = Payment
        fields = ["q", "method", "collection_mode", "received_on"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(client__name__icontains=value)
            | Q(invoice__number__icontains=value)
            | Q(reference__icontains=value)
        )


class SettlementFilter(django_filters.FilterSet):
    kind = django_filters.ChoiceFilter(
        choices=UpstreamSettlement.Kind.choices,
        empty_label="Both directions",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    settled_on = django_filters.DateFromToRangeFilter(
        label="Settled between",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = UpstreamSettlement
        fields = ["kind", "settled_on"]


class LedgerFilter(django_filters.FilterSet):
    """Shared date-range + text filter for the expense and income ledgers."""

    description = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(attrs={"placeholder": "Description", "class": "form-control"}),
    )
    occurred_on = django_filters.DateFromToRangeFilter(
        label="Between",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )


class ExpenseFilter(LedgerFilter):
    category = django_filters.ChoiceFilter(
        choices=Expense.Category.choices,
        empty_label="Any category",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Expense
        fields = ["description", "category", "occurred_on"]


class IncomeFilter(LedgerFilter):
    source = django_filters.ChoiceFilter(
        choices=Income.Source.choices,
        empty_label="Any source",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Income
        fields = ["description", "source", "occurred_on"]
