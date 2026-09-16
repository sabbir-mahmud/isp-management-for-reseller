"""Authentication and staff administration."""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from apps.core.mixins import CrudViewMixin, PageTitleMixin, StaffViewMixin

from .forms import StaffCreateForm, StaffUpdateForm, StyledAuthenticationForm
from .models import Profile
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


class StaffListView(StaffViewMixin, PageTitleMixin, ListView):
    permission_required = "users.view_profile"
    template_name = "users/staff_list.html"
    context_object_name = "profiles"
    paginate_by = 25
    page_title = "Staff"
    page_subtitle = "Who can sign in, and what they may do"

    def get_queryset(self):
        return Profile.objects.select_related("user").order_by("user__username")


class StaffCreateView(CrudViewMixin, CreateView):
    permission_required = "users.add_profile"
    model = User
    form_class = StaffCreateForm
    template_name = "form.html"
    success_url = reverse_lazy("staff_list")
    success_message = "Staff account created."
    page_title = "Add staff"


class StaffUpdateView(CrudViewMixin, UpdateView):
    permission_required = "users.change_profile"
    model = User
    form_class = StaffUpdateForm
    template_name = "form.html"
    success_url = reverse_lazy("staff_list")
    success_message = "Staff account updated."
    page_title = "Edit staff"
