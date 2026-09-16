"""View mixins: access control, actor stamping and HTMX-aware rendering."""

from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin


class StaffViewMixin(LoginRequiredMixin, PermissionRequiredMixin):
    """Every non-public view starts here.

    `raise_exception=False` keeps the redirect-to-login behaviour for anonymous
    users while returning a 403 for a signed-in user who lacks the permission,
    which is what Django's `PermissionRequiredMixin` does out of the box.
    """

    permission_denied_message = "You do not have permission to do that."


class ActorFormMixin:
    """Stamp `created_by` / `updated_by` from the request on save."""

    def form_valid(self, form):
        obj = form.instance
        if obj.pk is None and hasattr(obj, "created_by_id"):
            obj.created_by = self.request.user
        if hasattr(obj, "updated_by_id"):
            obj.updated_by = self.request.user
        return super().form_valid(form)


class HtmxTemplateMixin:
    """Render a fragment instead of the full page for HTMX requests.

    Set `htmx_template_name` on the view; list views use it to swap just the
    table body when the search form or a pagination link fires.
    """

    htmx_template_name: str | None = None

    def get_template_names(self):
        if self.htmx_template_name and getattr(self.request, "htmx", False):
            return [self.htmx_template_name]
        return super().get_template_names()


class PageTitleMixin:
    """Expose `page_title` / `page_subtitle` to the shared layout."""

    page_title: str = ""
    page_subtitle: str = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("page_title", self.page_title)
        context.setdefault("page_subtitle", self.page_subtitle)
        return context


class CrudViewMixin(StaffViewMixin, PageTitleMixin, SuccessMessageMixin, ActorFormMixin):
    """The full stack every create/update view needs, in one name."""
