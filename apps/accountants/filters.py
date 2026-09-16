import django_filters
from django import forms

from apps.core.choices import CollectionMode

from .models import Expense, Income, Invoice, Payment, UpstreamSettlement

#: `<input type="month">` posts `YYYY-MM`, which a plain DateField rejects —
#: and a rejected filter is silently dropped, showing every month instead.
MONTH_FORMATS = ["%Y-%m", "%Y-%m-%d"]


class InvoiceFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search invoices by number, client name, code or phone",
                "class": "form-control",
            }
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
        widget=forms.DateInput(attrs={"type": "month", "class": "form-control"}, format="%Y-%m"),
        input_formats=MONTH_FORMATS,
        method="by_month",
    )

    class Meta:
        model = Invoice
        fields = ["q", "status", "collection_mode", "period"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(number__icontains=value)
            | Q(client__name__icontains=value)
            | Q(client__client_code__icontains=value)
            | Q(client__phone__icontains=value)
        )

    def by_month(self, queryset, name, value):
        """Any date in the month selects that month's invoices."""
        return queryset.filter(period=value.replace(day=1))


class PaymentFilter(django_filters.FilterSet):
    #: Windows for `when`, shared with the summary chips on the payments page.
    WHEN_CHOICES = [
        ("today", "Today"),
        ("7d", "Last 7 days"),
        ("month", "This month"),
        ("last_month", "Last month"),
    ]

    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search payments by client, code, invoice or transaction ID",
                "class": "form-control",
            }
        ),
    )
    when = django_filters.ChoiceFilter(
        choices=WHEN_CHOICES,
        label="When",
        empty_label="Any time",
        method="by_when",
        widget=forms.Select(attrs={"class": "form-select"}),
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
        fields = ["q", "when", "method", "collection_mode", "received_on"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(client__name__icontains=value)
            | Q(client__client_code__icontains=value)
            | Q(client__phone__icontains=value)
            | Q(invoice__number__icontains=value)
            | Q(reference__icontains=value)
        )

    @staticmethod
    def window(key, today=None):
        """`(first, last)` dates of a `when` window, both inclusive."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.core.utils import month_start, previous_month

        today = today or timezone.localdate()
        if key == "today":
            return today, today
        if key == "7d":
            return today - timedelta(days=6), today
        if key == "month":
            return month_start(today), today
        if key == "last_month":
            first = previous_month(today)
            return first, month_start(today) - timedelta(days=1)
        return None

    def by_when(self, queryset, name, value):
        bounds = self.window(value)
        return queryset.filter(received_on__range=bounds) if bounds else queryset


class SettlementFilter(django_filters.FilterSet):
    # The shared toolbar puts a filterset's first field in the search slot.
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Search by reference or note", "class": "form-control"}
        ),
    )
    kind = django_filters.ChoiceFilter(
        choices=UpstreamSettlement.Kind.choices,
        label="Direction",
        empty_label="Both directions",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    period = django_filters.DateFilter(
        label="Month",
        method="by_month",
        input_formats=MONTH_FORMATS,
        widget=forms.DateInput(attrs={"type": "month", "class": "form-control"}, format="%Y-%m"),
    )
    settled_on = django_filters.DateFromToRangeFilter(
        label="Settled between",
        widget=django_filters.widgets.RangeWidget(attrs={"type": "date", "class": "form-control"}),
    )

    class Meta:
        model = UpstreamSettlement
        fields = ["q", "kind", "period", "settled_on"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(Q(reference__icontains=value) | Q(note__icontains=value))

    def by_month(self, queryset, name, value):
        return queryset.filter(period=value.replace(day=1))


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
