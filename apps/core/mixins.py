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


class SortableListMixin:
    """Column sorting driven by `?sort=`, restricted to a declared whitelist.

    The whitelist maps a short public key to the ORM expression it orders by.
    Passing user input straight to `order_by` would let a crafted query sort on
    a related table's columns — cheap to prevent, so prevented here.
    """

    sort_fields: dict[str, str] = {}
    default_sort: str = ""

    def get_sort_key(self) -> str:
        requested = self.request.GET.get("sort", "")
        if requested.lstrip("-") in self.sort_fields:
            return requested
        return self.default_sort

    def get_ordering(self):
        key = self.get_sort_key()
        if not key:
            return None
        field = self.sort_fields[key.lstrip("-")]
        return [f"-{field}" if key.startswith("-") else field]

    def apply_sort(self, queryset):
        ordering = self.get_ordering()
        return queryset.order_by(*ordering) if ordering else queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["sort"] = self.get_sort_key()
        return context


class CrudViewMixin(StaffViewMixin, PageTitleMixin, SuccessMessageMixin, ActorFormMixin):
    """The full stack every create/update view needs, in one name."""

    #: Where Cancel goes. Falling back to the referer sent people wherever they
    #: happened to come from, and to `/` when the browser sent no referer at
    #: all — so a view that knows the answer should say so.
    cancel_url = ""

    def get_cancel_url(self):
        if self.cancel_url:
            return str(self.cancel_url)
        obj = getattr(self, "object", None)
        if obj is not None and obj.pk and hasattr(obj, "get_absolute_url"):
            return obj.get_absolute_url()
        success = getattr(self, "success_url", "")
        # The referer is the last resort, read here rather than in the
        # template: a browser that sends none is a missing key, and resolving
        # one of those inside a `default:` argument raises.
        return str(success) if success else self.request.META.get("HTTP_REFERER", "/")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault("cancel_url", self.get_cancel_url())
        return context
