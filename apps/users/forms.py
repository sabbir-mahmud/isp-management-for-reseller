from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Profile

User = get_user_model()


class StyledAuthenticationForm(AuthenticationForm):
    """Django's login form, with the markup the layout expects."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {"class": "form-control form-control-lg", "autofocus": True, "placeholder": "Username"}
        )
        self.fields["password"].widget.attrs.update(
            {"class": "form-control form-control-lg", "placeholder": "Password"}
        )


class StaffCreateForm(UserCreationForm):
    """Create a staff login and its role in one step."""

    role = forms.ChoiceField(choices=Profile._meta.get_field("role").choices)
    phone = forms.CharField(max_length=20, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def save(self, commit=True):
        user = super().save(commit=commit)
        # `ensure_profile` already created the profile on first save.
        profile = user.profile
        profile.role = self.cleaned_data["role"]
        profile.phone = self.cleaned_data.get("phone", "")
        profile.save()
        return user


class StaffUpdateForm(forms.ModelForm):
    role = forms.ChoiceField(choices=Profile._meta.get_field("role").choices)
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "is_active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and hasattr(self.instance, "profile"):
            self.fields["role"].initial = self.instance.profile.role
            self.fields["phone"].initial = self.instance.profile.phone

    def save(self, commit=True):
        user = super().save(commit=commit)
        profile = user.profile
        profile.role = self.cleaned_data["role"]
        profile.phone = self.cleaned_data.get("phone", "")
        profile.save()
        return user
