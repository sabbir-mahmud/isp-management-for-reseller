"""Authentication and staff administration."""

import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import (
    CrudViewMixin,
    HtmxTemplateMixin,
    PageTitleMixin,
    SortableListMixin,
    StaffViewMixin,
)
from apps.core.utils import filtered_url

from .filters import StaffFilter
from .forms import StaffCreateForm, StaffUpdateForm, StyledAuthenticationForm, role_of
from .models import Profile, Role
from .roles import ROLE_DESCRIPTIONS
from .throttle import client_ip, is_locked, record_failure, reset

logger = logging.getLogger(__name__)
User = get_user_model()


class ThrottledLoginView(LoginView):
    """Django's `LoginView` plus a failure counter.

    Using the framework's view (instead of the hand-rolled one this project
    started with) means `next` validation, session rotation and the redirect
    for already-authenticated users are all handled upstream.
    """

    template_name = "users/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        username = request.POST.get("username", "")
        ip = client_ip(request)
        if is_locked(username, ip):
            logger.warning("login lockout user=%s ip=%s", username, ip)
            form = self.get_form()
            form.full_clean()
            form.add_error(None, "Too many failed attempts. Try again in a few minutes.")
            return self.render_to_response(self.get_context_data(form=form))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        reset(form.cleaned_data.get("username", ""), client_ip(self.request))
        logger.info("login success user=%s", form.get_user().get_username())
        return super().form_valid(form)

    def form_invalid(self, form):
        username = form.data.get("username", "")
        ip = client_ip(self.request)
        record_failure(username, ip)
        logger.warning("login failure user=%s ip=%s", username, ip)
        return super().form_invalid(form)


class SignOutView(LogoutView):
    """POST-only sign out (Django refuses GET here, which is the right CSRF posture)."""

    next_page = reverse_lazy("login")


class ChangePasswordView(PageTitleMixin, PasswordChangeView):
    template_name = "users/password_change.html"
    success_url = reverse_lazy("dashboard")
    page_title = "Change password"


class StaffListView(StaffViewMixin, PageTitleMixin, SortableListMixin, HtmxTemplateMixin, ListView):
    """Every account, including one that predates the profile table.

    Listing users rather than profiles is deliberate: a superuser created
    before `ensure_profile` existed has no profile, and a profile-based list
    left the very account that can manage staff off the staff page.
    """

    permission_required = "users.view_profile"
    template_name = "users/staff_list.html"
    htmx_template_name = "users/partials/staff_rows.html"
    context_object_name = "people"
    paginate_by = 25
    page_title = "Staff"
    page_subtitle = "Who can sign in, and what they may do"

    sort_fields = {
        "name": "first_name",
        "username": "username",
        "role": "role_rank",
        "seen": "last_login",
        "joined": "date_joined",
    }
    default_sort = "role"

    #: Most access first, so the owners head an unsorted list.
    ROLE_ORDER = [Role.OWNER, Role.MANAGER, Role.ACCOUNTANT, Role.SUPPORT]

    def get_queryset(self):
        queryset = User.objects.select_related("profile").annotate(
            role_rank=Case(
                *[
                    When(profile__role=role, then=Value(rank))
                    for rank, role in enumerate(self.ROLE_ORDER)
                ],
                # No profile: a superuser is an owner; anyone else sorts last.
                When(is_superuser=True, then=Value(0)),
                default=Value(len(self.ROLE_ORDER)),
                output_field=IntegerField(),
            )
        )
        self.filterset = StaffFilter(self.request.GET, queryset=queryset)
        ordering = self.get_ordering() or []
        # Nulls last: "never signed in" belongs at the end either way.
        ordering = [
            F(key.lstrip("-")).desc(nulls_last=True)
            if key.startswith("-")
            else F(key).asc(nulls_last=True)
            for key in ordering
        ]
        return self.filterset.qs.order_by(*ordering, "username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter"] = self.filterset
        since = timezone.now() - timedelta(days=30)
        # Same rule as the last-owner guard: a superuser can always manage staff.
        owner = Q(profile__role=Role.OWNER) | Q(is_superuser=True)
        totals = User.objects.aggregate(
            total=Count("pk"),
            active=Count("pk", filter=Q(is_active=True)),
            disabled=Count("pk", filter=Q(is_active=False)),
            owners=Count("pk", filter=owner & Q(is_active=True)),
            recent=Count("pk", filter=Q(is_active=True, last_login__gte=since)),
            never=Count("pk", filter=Q(is_active=True, last_login__isnull=True)),
            **{
                f"role_{role}": Count("pk", filter=Q(profile__role=role, is_active=True))
                for role in self.ROLE_ORDER
            },
        )
        context["totals"] = totals

        # The role guide doubles as the role filter.
        current = self.request.GET.get("role", "")
        context["roles"] = [
            {
                "value": role,
                "label": Role(role).label,
                "description": ROLE_DESCRIPTIONS[role],
                "count": totals[f"role_{role}"],
                "is_active": current == role,
                "url": filtered_url(self.request, role=None if current == role else role),
            }
            for role in self.ROLE_ORDER
        ]
        context["row_noun"], context["row_noun_plural"] = "person", "people"
        return context


class StaffFormViewMixin(CrudViewMixin):
    """Hands the signed-in user to the form, for its self-lockout guards."""

    model = User
    template_name = "users/staff_form.html"
    success_url = reverse_lazy("staff_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["acting_user"] = self.request.user
        return kwargs


class StaffCreateView(StaffFormViewMixin, CreateView):
    permission_required = "users.add_profile"
    form_class = StaffCreateForm
    success_message = "%(username)s can now sign in."
    page_title = "Add staff"
    page_subtitle = "A login for someone who works with you"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_label"] = "Create account"
        return context


class StaffUpdateView(StaffFormViewMixin, UpdateView):
    permission_required = "users.change_profile"
    form_class = StaffUpdateForm
    page_title = "Edit staff"

    def get_success_message(self, cleaned_data):
        return f"{self.object.get_full_name() or self.object.username}'s account was updated."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        person = self.object
        context["person"] = person
        context["person_role"] = role_of(person)
        context["is_self"] = person.pk == self.request.user.pk
        context["page_subtitle"] = (
            f"{person.get_full_name()} · {person.username}"
            if person.get_full_name()
            else person.username
        )
        context["submit_label"] = "Save changes"
        if not Profile.objects.filter(user=person).exists():
            context["notice"] = (
                "This account has no staff profile yet, so it has no role on record. "
                "Saving gives it the role chosen below."
            )
        return context
