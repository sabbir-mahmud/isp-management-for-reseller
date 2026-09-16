from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models import Q

from apps.accounts.forms import BootstrapFormMixin

from .models import Profile, Role
from .roles import ROLE_DESCRIPTIONS

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


def role_of(user) -> str:
    """A user's role, reading a superuser without a profile as an owner."""
    profile = Profile.objects.filter(user=user).first() if user.pk else None
    if profile is not None:
        return profile.role
    return Role.OWNER if user.is_superuser else Role.SUPPORT


def other_active_owners(user):
    """Active accounts, other than `user`, that can still manage staff."""
    return (
        User.objects.filter(is_active=True)
        .filter(Q(profile__role=Role.OWNER) | Q(is_superuser=True))
        .exclude(pk=user.pk)
    )


class StaffFormMixin(BootstrapFormMixin, forms.Form):
    """What the create and update forms share: role, phone and the save.

    `acting_user` is whoever is filling the form in, so the update form can
    stop them locking themselves — or everyone — out.
    """

    role = forms.ChoiceField(
        choices=Role.choices,
        widget=forms.RadioSelect,
        help_text="What they can see and change. Each role is described below.",
    )
    phone = forms.CharField(max_length=20, required=False)

    wide_fields = frozenset({"role", "email"})
    field_addons = {"role": "users/partials/role_guide.html"}

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        self.role_descriptions = ROLE_DESCRIPTIONS
        self.fields["first_name"].widget.attrs.setdefault("placeholder", "e.g. Karim")
        self.fields["last_name"].widget.attrs.setdefault("placeholder", "e.g. Hossain")
        self.fields["email"].widget.attrs.setdefault("placeholder", "Optional")
        self.fields["phone"].widget.attrs.update(
            {"placeholder": "e.g. 01712345678", "inputmode": "tel", "autocomplete": "off"}
        )
        self.fields["phone"].label = "Phone"

    def save(self, commit=True):
        user = super().save(commit=commit)
        # `ensure_profile` makes one for new users; an account created before
        # that signal existed (a first superuser, say) may still lack one.
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = self.cleaned_data["role"]
        profile.phone = self.cleaned_data.get("phone", "")
        profile.save()
        return user


class StaffCreateForm(StaffFormMixin, UserCreationForm):
    """Create a staff login and its role in one step."""

    fieldsets = (
        {
            "title": "Sign-in",
            "caption": "The username they type at the login screen, and a first "
            "password. They can change it after signing in.",
            "fields": ["username", "password1", "password2"],
        },
        {
            "title": "Person",
            "caption": "Who this is, so the name appears on what they record.",
            "fields": ["first_name", "last_name", "email", "phone"],
        },
        {
            "title": "Role",
            "caption": "Start with the least they need; it can be raised later.",
            "fields": ["role"],
        },
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].initial = Role.SUPPORT
        self.fields["username"].widget.attrs.update(
            {"placeholder": "e.g. karim", "autocomplete": "off", "autofocus": True}
        )
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs["autocomplete"] = "new-password"
        # Django's password help is a bulleted HTML list; one line reads better here.
        self.fields[
            "password1"
        ].help_text = "At least 8 characters, not only numbers, and not close to their name."
        self.fields["password2"].help_text = ""


class StaffUpdateForm(StaffFormMixin, forms.ModelForm):
    fieldsets = (
        {
            "title": "Person",
            "caption": "Who this is, so the name appears on what they record.",
            "fields": ["first_name", "last_name", "email", "phone"],
        },
        {
            "title": "Role",
            "caption": "Changing it takes effect on their next page load.",
            "fields": ["role"],
        },
        {
            "title": "Access",
            "caption": "A disabled account keeps its history but cannot sign in. "
            "Prefer it to deleting someone who has left.",
            "fields": ["is_active"],
        },
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "is_active")
        labels = {"is_active": "Can sign in"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.instance
        self.fields["role"].initial = role_of(user)
        profile = Profile.objects.filter(user=user).first() if user.pk else None
        self.fields["phone"].initial = profile.phone if profile else ""
        self.fields["is_active"].help_text = "Untick when someone leaves."

        if self.acting_user is not None and self.acting_user.pk == user.pk:
            # Your own role and access are changed by another owner, never by
            # you: one mis-click here and nobody can put it back.
            for name in ("role", "is_active"):
                self.fields[name].disabled = True
            self.fields["role"].help_text = "Your own role is changed by another owner."
            self.fields["is_active"].help_text = "You cannot disable your own account."

    def clean(self):
        cleaned = super().clean()
        user = self.instance
        was_owner = user.is_active and role_of(user) == Role.OWNER
        stays_owner = cleaned.get("is_active", user.is_active) and (
            cleaned.get("role") == Role.OWNER or user.is_superuser
        )
        if was_owner and not stays_owner and not other_active_owners(user).exists():
            raise forms.ValidationError(
                f"{user.get_full_name() or user.username} is the only owner who can sign in. "
                "Make someone else an owner first, or nobody will be able to manage staff."
            )
        return cleaned
