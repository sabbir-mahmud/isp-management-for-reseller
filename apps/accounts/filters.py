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
            attrs={"placeholder": "Name, code, phone, username or NID", "class": "form-control"}
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
    name = django_filters.CharFilter(
        lookup_expr="icontains",
        widget=forms.TextInput(attrs={"placeholder": "Package name", "class": "form-control"}),
    )
    is_active = django_filters.BooleanFilter(
        label="Active",
        widget=forms.Select(
            choices=[("", "Any"), (True, "Active"), (False, "Retired")],
            attrs={"class": "form-select"},
        ),
    )

    class Meta:
        model = Package
        fields = ["name", "is_active"]
