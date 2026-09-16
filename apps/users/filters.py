import django_filters
from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Role


class StaffFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Search staff by name, username, email or phone",
                "class": "form-control",
            }
        ),
    )
    role = django_filters.ChoiceFilter(
        field_name="profile__role",
        choices=Role.choices,
        label="Role",
        empty_label="Any role",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    access = django_filters.ChoiceFilter(
        choices=[("active", "Can sign in"), ("disabled", "Disabled")],
        label="Access",
        empty_label="Everyone",
        method="by_access",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = get_user_model()
        fields = ["q", "role", "access"]

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(
            Q(username__icontains=value)
            | Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
            | Q(profile__phone__icontains=value)
        )

    def by_access(self, queryset, name, value):
        return queryset.filter(is_active=value == "active")
