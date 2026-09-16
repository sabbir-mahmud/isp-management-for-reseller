import django_filters
from django import forms

from apps.warehouse.models import Pop

from .models import Client, Package


class ClientFilter(django_filters.FilterSet):
    """Search and narrow the client list.

    `q` is a single box covering the five fields an operator actually types
    into, so the common case is one input rather than five.
    """

    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search clients by name, code, phone, username or NID",
                "class": "form-control",
            }
        ),
    )
    status = django_filters.ChoiceFilter(
        choices=Client.Status.choices,
        empty_label="Any status",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    pop = django_filters.ModelChoiceFilter(
        queryset=Pop.objects.filter(is_active=True),
        empty_label="Any POP",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    package = django_filters.ModelChoiceFilter(
        queryset=Package.objects.active(),
        field_name="subscriptions__package",
        label="Package",
        empty_label="Any package",
        distinct=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Client
        fields = ["q", "status", "pop", "package"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(client_code__icontains=value)
            | Q(phone__icontains=value)
            | Q(username__icontains=value)
            | Q(nid__icontains=value)
            | Q(email__icontains=value)
        )


class PackageFilter(django_filters.FilterSet):
    """Search across the fields an operator would type, not just the name."""

    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Search packages by name or description", "class": "form-control"}
        ),
    )
    is_active = django_filters.ChoiceFilter(
        label="Availability",
        choices=[("true", "On sale"), ("false", "Retired")],
        empty_label="Any availability",
        method="by_availability",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    speed = django_filters.ChoiceFilter(
        label="Speed",
        method="by_speed",
        empty_label="Any speed",
        choices=[
            ("0-20", "Up to 20 Mbps"),
            ("21-50", "21 – 50 Mbps"),
            ("51-", "Over 50 Mbps"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Package
        fields = ["q", "is_active", "speed"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(description__icontains=value))

    def by_availability(self, queryset, name, value):
        return queryset.filter(is_active=value == "true")

    def by_speed(self, queryset, name, value):
        low, _, high = value.partition("-")
        queryset = queryset.filter(bandwidth_mbps__gte=int(low))
        return queryset.filter(bandwidth_mbps__lte=int(high)) if high else queryset


class PopFilter(django_filters.FilterSet):
    """POPs had no filter at all, which stops working the moment there are 150."""

    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Search POPs by name, code or address", "class": "form-control"}
        ),
    )
    parent = django_filters.ModelChoiceFilter(
        queryset=Pop.objects.filter(is_active=True),
        label="Upstream",
        empty_label="Any upstream",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    is_active = django_filters.ChoiceFilter(
        label="Status",
        choices=[("true", "Active"), ("false", "Inactive")],
        empty_label="Any status",
        method="by_status",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Pop
        fields = ["q", "parent", "is_active"]

    def search(self, queryset, name, value):
        from django.db.models import Q

        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(code__icontains=value) | Q(address__icontains=value)
        )

    def by_status(self, queryset, name, value):
        return queryset.filter(is_active=value == "true")
