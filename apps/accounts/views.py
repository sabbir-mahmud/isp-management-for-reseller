"""Customer, package and POP screens.

Every view is permission-gated by name; `login_required` alone (as before)
gave a support technician the same power as the owner.
"""

from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Case, Count, DecimalField, F, Q, Value, When
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accountants.services import change_package
from apps.core.aggregates import money_sum
from apps.core.chips import build_chips
from apps.core.mixins import (
    CrudViewMixin,
    HtmxTemplateMixin,
    PageTitleMixin,
    SortableListMixin,
    StaffViewMixin,
)
from apps.warehouse.models import Pop

from .filters import ClientFilter, PackageFilter, PopFilter
from .forms import ClientForm, PackageForm, PopForm
from .models import Client, Package
from .services import ProvisioningError, assign_onu, set_client_status


class FilteredListView(StaffViewMixin, PageTitleMixin, HtmxTemplateMixin, ListView):
    """List + filter + paginate, wired the same way on every screen."""

    filterset_class = None
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset()
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter"] = self.filterset
        return context


# ---------------------------------------------------------------------------#
# Clients
# ---------------------------------------------------------------------------#


class ClientListView(SortableListMixin, FilteredListView):
    permission_required = "accounts.view_client"
    model = Client
    filterset_class = ClientFilter
    template_name = "accounts/client_list.html"
    htmx_template_name = "accounts/partials/client_rows.html"
    context_object_name = "clients"
    page_title = "Clients"
    page_subtitle = "Everyone connected, and what they are on"

    sort_fields = {
        "name": "name",
        "code": "client_code",
        "status": "status",
        "pop": "pop__name",
        "owes": "outstanding",
        "joined": "connection_date",
    }
    default_sort = "-joined"

    def get_queryset(self):
        self.filterset = self.filterset_class(
            self.request.GET, queryset=Client.objects.with_related()
        )
        return self.apply_sort(self.filterset.qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = Client.objects.aggregate(
            total=Count("pk"),
            active=Count("pk", filter=Q(status=Client.Status.ACTIVE)),
            suspended=Count("pk", filter=Q(status=Client.Status.SUSPENDED)),
            pending=Count("pk", filter=Q(status=Client.Status.PENDING)),
            terminated=Count("pk", filter=Q(status=Client.Status.TERMINATED)),
        )
        context["status_counts"] = counts
        context["chips"] = build_chips(
            self.request,
            "status",
            [
                {"label": "All clients", "value": counts["total"], "match": None},
                {
                    "label": "Active",
                    "value": counts["active"],
                    "match": "active",
                    "tone": "success",
                },
                {
                    "label": "Suspended",
                    "value": counts["suspended"],
                    "match": "suspended",
                    "tone": "warning",
                },
                {"label": "Pending install", "value": counts["pending"], "match": "pending"},
                {
                    "label": "Terminated",
                    "value": counts["terminated"],
                    "match": "terminated",
                    "tone": "muted",
                },
            ],
        )
        context["row_noun"], context["row_noun_plural"] = "client", "clients"
        return context


class ClientDetailView(StaffViewMixin, PageTitleMixin, DetailView):
    permission_required = "accounts.view_client"
    model = Client
    template_name = "accounts/client_detail.html"
    context_object_name = "client"

    def get_queryset(self):
        return Client.objects.with_related()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        context["page_title"] = client.name
        context["page_subtitle"] = f"{client.client_code} · {client.username}"
        context["invoices"] = client.invoices.order_by("-period")[:12]
        context["payments"] = client.payments.select_related("invoice")[:12]
        context["subscriptions"] = client.subscriptions.select_related("package")
        return context


class ClientCreateView(CrudViewMixin, CreateView):
    permission_required = "accounts.add_client"
    model = Client
    form_class = ClientForm
    template_name = "form.html"
    success_message = "Client %(name)s was added."
    page_title = "Add client"
    page_subtitle = "Their details, their plan and their billing day, in one pass"
    cancel_url = reverse_lazy("client_list")

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        change_package(
            self.object,
            form.cleaned_data["package"],
            monthly_price=form.cleaned_data["monthly_price"],
            discount=form.cleaned_data["discount"],
            commission_percent=form.cleaned_data.get("commission_percent"),
            actor=self.request.user,
        )
        self._sync_onu(form)
        return response

    def _sync_onu(self, form):
        try:
            assign_onu(self.object, form.cleaned_data.get("onu"), actor=self.request.user)
        except ProvisioningError as exc:
            messages.warning(self.request, str(exc))


class ClientUpdateView(ClientCreateView, UpdateView):
    """Same form and side effects as create; only the permission differs."""

    permission_required = "accounts.change_client"
    success_message = "Client %(name)s was updated."
    page_title = "Edit client"

    def get_queryset(self):
        return Client.objects.all()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Whose record this is, so a form reached from a list of 200 names
        # says which one you opened.
        context["page_subtitle"] = f"{self.object.name} · {self.object.client_code}"
        return context


class ClientDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "accounts.delete_client"
    model = Client
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("client_list")
    page_title = "Remove client"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["warning"] = (
            "The client is archived, not erased — their invoices and payments stay on record."
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, f"{self.object.name} was archived.")
        return super().form_valid(form)


class ClientStatusView(StaffViewMixin, DetailView):
    """Flip a client's status from the list without opening the full form."""

    permission_required = "accounts.change_client"
    model = Client
    http_method_names = ["post"]

    def post(self, request, *args, **kwargs):
        client = self.get_object()
        status = request.POST.get("status")
        if status not in Client.Status.values:
            messages.error(request, "Unknown status.")
        else:
            set_client_status(client, status, actor=request.user)
            messages.success(request, f"{client.name} is now {client.get_status_display()}.")
        return redirect(request.POST.get("next") or "client_list")


# ---------------------------------------------------------------------------#
# Packages
# ---------------------------------------------------------------------------#


class PackageListView(SortableListMixin, FilteredListView):
    permission_required = "accounts.view_package"
    model = Package
    filterset_class = PackageFilter
    template_name = "accounts/package_list.html"
    context_object_name = "packages"
    page_title = "Packages"
    page_subtitle = "Plans you sell, and what they earn"

    sort_fields = {
        "name": "name",
        "speed": "bandwidth_mbps",
        "price": "monthly_price",
        "subscribers": "subscribers",
        "revenue": "monthly_revenue",
    }

    def get_queryset(self):
        live = Q(subscriptions__status="active")
        queryset = Package.objects.annotate(
            subscribers=Count("subscriptions", filter=live, distinct=True),
            monthly_revenue=money_sum(
                Case(
                    When(
                        live, then=F("subscriptions__monthly_price") - F("subscriptions__discount")
                    ),
                    default=Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
        ).order_by("-is_active", "monthly_price", "name")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.apply_sort(self.filterset.qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = list(context["packages"])
        # The share bars need a denominator, and it has to be the largest plan
        # on the page rather than the total — otherwise every bar is a sliver.
        context["busiest"] = max((row.subscribers for row in rows), default=0) or 1

        totals = Package.objects.aggregate(
            plans=Count("pk"),
            active=Count("pk", filter=Q(is_active=True)),
            retired=Count("pk", filter=Q(is_active=False)),
        )
        totals["subscribers"] = sum(row.subscribers for row in rows)
        totals["revenue"] = sum((row.monthly_revenue for row in rows), start=Decimal("0.00"))
        context["totals"] = totals
        context["chips"] = build_chips(
            self.request,
            "is_active",
            [
                {"label": "All packages", "value": totals["plans"], "match": None},
                {"label": "On sale", "value": totals["active"], "match": "true", "tone": "success"},
                {"label": "Retired", "value": totals["retired"], "match": "false", "tone": "muted"},
            ],
        )
        context["chip_group"] = "availability"
        context["row_noun"], context["row_noun_plural"] = "package", "packages"
        return context


class PackageCreateView(CrudViewMixin, CreateView):
    permission_required = "accounts.add_package"
    model = Package
    form_class = PackageForm
    template_name = "form.html"
    success_url = reverse_lazy("package_list")
    success_message = "Package %(name)s was created."
    page_title = "Add package"
    page_subtitle = "Speed, price and commission for a plan you sell"


class PackageUpdateView(CrudViewMixin, UpdateView):
    permission_required = "accounts.change_package"
    model = Package
    form_class = PackageForm
    template_name = "form.html"
    success_url = reverse_lazy("package_list")
    success_message = "Package %(name)s was updated."
    page_title = "Edit package"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_subtitle"] = str(self.object)
        context["notice"] = (
            "Changing the price here affects new subscriptions only. Existing clients "
            "keep the price agreed with them until you change it on their record."
        )
        return context


class PackageDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "accounts.delete_package"
    model = Package
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("package_list")
    page_title = "Delete package"

    def form_valid(self, form):
        package = self.get_object()
        if package.subscriptions.exists():
            # PROTECT would raise at the database; say why in plain language.
            messages.error(
                self.request,
                f"{package.name} still has subscribers. Move them to another package, "
                "or mark this one inactive instead.",
            )
            return redirect("package_list")
        messages.success(self.request, f"{package.name} was deleted.")
        return super().form_valid(form)


# ---------------------------------------------------------------------------#
# POPs
# ---------------------------------------------------------------------------#


class PopListView(FilteredListView):
    permission_required = "warehouse.view_pop"
    model = Pop
    filterset_class = PopFilter
    template_name = "accounts/pop_list.html"
    context_object_name = "pops"
    paginate_by = 50
    page_title = "POPs"
    page_subtitle = "Points of presence and their client load"

    def get_queryset(self):
        queryset = (
            Pop.objects.select_related("parent")
            .annotate(
                clients_total=Count("clients", distinct=True),
                clients_active=Count("clients", filter=Q(clients__status="active"), distinct=True),
            )
            .order_by("name")
        )
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        rows = list(self.filterset.qs)

        # The estate's shape is the point, so the tree is built across the
        # whole result and *then* paginated. Ordering a single page would put
        # a child on page 2 under a parent left behind on page 1.
        self.all_rows = rows
        return self._as_tree(rows)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        rows = self.all_rows
        context["busiest"] = max((row.clients_total for row in rows), default=0) or 1

        totals = Pop.objects.aggregate(
            pops=Count("pk"),
            active=Count("pk", filter=Q(is_active=True)),
            inactive=Count("pk", filter=Q(is_active=False)),
        )
        totals["clients"] = sum(row.clients_total for row in rows)
        totals["unattached"] = sum(1 for row in rows if row.clients_total == 0)
        context["totals"] = totals
        context["chips"] = build_chips(
            self.request,
            "is_active",
            [
                {"label": "All POPs", "value": totals["pops"], "match": None},
                {"label": "Active", "value": totals["active"], "match": "true", "tone": "success"},
                {
                    "label": "Inactive",
                    "value": totals["inactive"],
                    "match": "false",
                    "tone": "muted",
                },
            ],
        )
        context["chip_group"] = "status"
        context["row_noun"], context["row_noun_plural"] = "POP", "POPs"
        return context

    @staticmethod
    def _as_tree(rows):
        """Order parents before their children, and tag each row's depth.

        Done in Python over the fetched rows rather than as a recursive query:
        an estate is hundreds of POPs, not millions.
        """
        children = {}
        for row in rows:
            children.setdefault(row.parent_id, []).append(row)

        ordered = []

        def walk(parent_id, depth):
            for row in children.get(parent_id, []):
                row.depth = depth
                ordered.append(row)
                walk(row.pk, depth + 1)

        walk(None, 0)
        # A row whose parent was filtered out still has to appear, at the root.
        seen = {row.pk for row in ordered}
        for row in rows:
            if row.pk not in seen:
                row.depth = 0
                ordered.append(row)
        return ordered


class PopCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_pop"
    model = Pop
    form_class = PopForm
    template_name = "form.html"
    success_url = reverse_lazy("pop_list")
    success_message = "POP %(name)s was created."
    page_title = "Add POP"
    page_subtitle = "A point of presence, and the POP it takes its feed from"


class PopUpdateView(CrudViewMixin, UpdateView):
    permission_required = "warehouse.change_pop"
    model = Pop
    form_class = PopForm
    template_name = "form.html"
    success_url = reverse_lazy("pop_list")
    success_message = "POP %(name)s was updated."
    page_title = "Edit POP"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_subtitle"] = self.object.name
        return context


class PopDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "warehouse.delete_pop"
    model = Pop
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("pop_list")
    page_title = "Delete POP"

    def form_valid(self, form):
        pop = self.get_object()
        if pop.clients.exists():
            messages.error(
                self.request,
                f"{pop.name} still has clients attached. Move them first, or mark it inactive.",
            )
            return redirect("pop_list")
        return super().form_valid(form)


def client_or_404(pk) -> Client:
    return get_object_or_404(Client.objects.with_related(), pk=pk)
