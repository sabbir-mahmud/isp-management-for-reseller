"""Customer, package and POP screens.

Every view is permission-gated by name; `login_required` alone (as before)
gave a support technician the same power as the owner.
"""

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accountants.services import change_package
from apps.core.mixins import CrudViewMixin, HtmxTemplateMixin, PageTitleMixin, StaffViewMixin
from apps.warehouse.models import Pop

from .filters import ClientFilter, PackageFilter
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


class ClientListView(FilteredListView):
    permission_required = "accounts.view_client"
    model = Client
    filterset_class = ClientFilter
    template_name = "accounts/client_list.html"
    htmx_template_name = "accounts/partials/client_rows.html"
    context_object_name = "clients"
    page_title = "Clients"
    page_subtitle = "Everyone connected, and what they are on"

    def get_queryset(self):
        self.filterset = self.filterset_class(
            self.request.GET, queryset=Client.objects.with_related()
        )
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["status_counts"] = Client.objects.aggregate(
            total=Count("pk"),
            active=Count("pk", filter=Q(status=Client.Status.ACTIVE)),
            suspended=Count("pk", filter=Q(status=Client.Status.SUSPENDED)),
            pending=Count("pk", filter=Q(status=Client.Status.PENDING)),
        )
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


class PackageListView(FilteredListView):
    permission_required = "accounts.view_package"
    model = Package
    filterset_class = PackageFilter
    template_name = "accounts/package_list.html"
    context_object_name = "packages"
    page_title = "Packages"
    page_subtitle = "Plans you sell, and what they earn"

    def get_queryset(self):
        queryset = Package.objects.annotate(
            subscribers=Count(
                "subscriptions", filter=Q(subscriptions__status="active"), distinct=True
            )
        ).order_by("-is_active", "monthly_price", "name")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs


class PackageCreateView(CrudViewMixin, CreateView):
    permission_required = "accounts.add_package"
    model = Package
    form_class = PackageForm
    template_name = "form.html"
    success_url = reverse_lazy("package_list")
    success_message = "Package %(name)s was created."
    page_title = "Add package"


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


class PopListView(StaffViewMixin, PageTitleMixin, ListView):
    permission_required = "warehouse.view_pop"
    model = Pop
    template_name = "accounts/pop_list.html"
    context_object_name = "pops"
    paginate_by = 50
    page_title = "POPs"
    page_subtitle = "Points of presence and their client load"

    def get_queryset(self):
        return (
            Pop.objects.select_related("parent")
            .annotate(
                clients_total=Count("clients", distinct=True),
                clients_active=Count("clients", filter=Q(clients__status="active"), distinct=True),
            )
            .order_by("name")
        )


class PopCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_pop"
    model = Pop
    form_class = PopForm
    template_name = "form.html"
    success_url = reverse_lazy("pop_list")
    success_message = "POP %(name)s was created."
    page_title = "Add POP"


class PopUpdateView(CrudViewMixin, UpdateView):
    permission_required = "warehouse.change_pop"
    model = Pop
    form_class = PopForm
    template_name = "form.html"
    success_url = reverse_lazy("pop_list")
    success_message = "POP %(name)s was updated."
    page_title = "Edit POP"


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
