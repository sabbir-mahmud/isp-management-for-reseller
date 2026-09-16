from datetime import timedelta

import django_filters
from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.core.choices import CollectionMode
from apps.core.utils import add_months, month_start, previous_month

from .models import Expense, Income, Invoice, Payment, UpstreamSettlement

#: `<input type="month">` posts `YYYY-MM`, which a plain DateField rejects —
#: and a rejected filter is silently dropped, showing every month instead.
MONTH_FORMATS = ["%Y-%m", "%Y-%m-%d"]


def date_window(key, today=None):
    """`(first, last)` dates, both inclusive, of a named window — or None.

    Shared by the `when` filters and the summary chips built from them, so a
    chip and the filter it applies can never disagree about a boundary.
    """
    today = today or timezone.localdate()
    if key == "today":
        return today, today
    if key == "7d":
        return today - timedelta(days=6), today
    if key == "month":
        return month_start(today), today
    if key == "last_month":
        return previous_month(today), month_start(today) - timedelta(days=1)
    if key == "3m":
        return add_months(month_start(today), -2), today
    if key == "year":
        return today.replace(month=1, day=1), today
    return None


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

    def by_when(self, queryset, name, value):
        bounds = date_window(value)
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
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(Q(reference__icontains=value) | Q(note__icontains=value))

    def by_month(self, queryset, name, value):
        return queryset.filter(period=value.replace(day=1))


class LedgerFilter(django_filters.FilterSet):
    """Shared search, time window and date range for the two manual ledgers."""

    WHEN_CHOICES = [
        ("month", "This month"),
        ("last_month", "Last month"),
        ("3m", "Last 3 months"),
        ("year", "This year"),
    ]

    # Named `description` for the links that already use it; it searches the
    # note as well, which is where the detail usually is.
    description = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Search by description or note", "class": "form-control"}
        ),
    )
    #: Choosing Custom in `when` reveals the `occurred_on` range in the toolbar.
    custom_range = ("when", "occurred_on")

    when = django_filters.ChoiceFilter(
        # Custom filters nothing itself; it hands over to the date range.
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

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(Q(description__icontains=value) | Q(note__icontains=value))

    def by_when(self, queryset, name, value):
        bounds = date_window(value)
        return queryset.filter(occurred_on__range=bounds) if bounds else queryset


class ExpenseFilter(LedgerFilter):
    category = django_filters.ChoiceFilter(
        choices=Expense.Category.choices,
        empty_label="Any category",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Expense
        fields = ["description", "when", "category", "occurred_on"]


class IncomeFilter(LedgerFilter):
    source = django_filters.ChoiceFilter(
        choices=Income.Source.choices,
        empty_label="Any source",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Income
        fields = ["description", "when", "source", "occurred_on"]
