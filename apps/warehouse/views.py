"""Inventory screens: stock, serialised ONUs and the movement ledger."""

from django.contrib import messages
from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.accounts.views import FilteredListView
from apps.core.aggregates import money_sum
from apps.core.chips import build_chips
from apps.core.mixins import CrudViewMixin, PageTitleMixin, SortableListMixin, StaffViewMixin
from apps.core.utils import filtered_url

from .filters import OnuFilter, ProductFilter, StockMovementFilter
from .forms import CategoryForm, OnuForm, ProductForm, StockMovementForm
from .models import Category, Onu, Product, StockMovement


class ProductListView(FilteredListView):
    permission_required = "warehouse.view_product"
    model = Product
    filterset_class = ProductFilter
    template_name = "warehouse/product_list.html"
    htmx_template_name = "warehouse/partials/product_rows.html"
    context_object_name = "products"
    page_title = "Stock"
    page_subtitle = "Cables, routers, spares — what is on the shelf"

    def get_queryset(self):
        queryset = Product.objects.select_related("category")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["totals"] = Product.objects.aggregate(
            skus=Count("pk"),
            units=Sum("quantity", default=Value(0)),
            value=money_sum(F("quantity") * F("unit_price")),
        )
        context["low_stock"] = Product.objects.low_stock().count()
        return context


class ProductCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_product"
    model = Product
    form_class = ProductForm
    template_name = "form.html"
    success_url = reverse_lazy("product_list")
    success_message = "%(name)s was added to stock."
    page_title = "Add stock item"

    def form_valid(self, form):
        response = super().form_valid(form)
        opening = form.cleaned_data.get("opening_quantity") or 0
        if opening:
            StockMovement.objects.create(
                product=self.object,
                kind=StockMovement.Kind.IN,
                quantity=opening,
                reason="Opening stock",
                created_by=self.request.user,
            )
        return response


class ProductUpdateView(CrudViewMixin, UpdateView):
    permission_required = "warehouse.change_product"
    model = Product
    form_class = ProductForm
    template_name = "form.html"
    success_url = reverse_lazy("product_list")
    success_message = "%(name)s was updated."
    page_title = "Edit stock item"


class ProductDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "warehouse.delete_product"
    model = Product
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("product_list")
    page_title = "Delete stock item"


# ---------------------------------------------------------------------------#
# Categories
# ---------------------------------------------------------------------------#


class CategoryListView(StaffViewMixin, PageTitleMixin, ListView):
    permission_required = "warehouse.view_category"
    model = Category
    template_name = "warehouse/category_list.html"
    context_object_name = "categories"
    paginate_by = 50
    page_title = "Categories"

    def get_queryset(self):
        return Category.objects.annotate(products_count=Count("products")).order_by("name")


class CategoryCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_category"
    model = Category
    form_class = CategoryForm
    template_name = "form.html"
    success_url = reverse_lazy("category_list")
    success_message = "Category %(name)s was created."
    page_title = "Add category"


class CategoryUpdateView(CrudViewMixin, UpdateView):
    permission_required = "warehouse.change_category"
    model = Category
    form_class = CategoryForm
    template_name = "form.html"
    success_url = reverse_lazy("category_list")
    success_message = "Category %(name)s was updated."
    page_title = "Edit category"


class CategoryDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "warehouse.delete_category"
    model = Category
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("category_list")
    page_title = "Delete category"

    def form_valid(self, form):
        category = self.get_object()
        if category.products.exists():
            messages.error(self.request, f"{category.name} still holds products; move them first.")
            return redirect("category_list")
        return super().form_valid(form)


# ---------------------------------------------------------------------------#
# ONUs
# ---------------------------------------------------------------------------#


class OnuListView(SortableListMixin, FilteredListView):
    permission_required = "warehouse.view_onu"
    model = Onu
    filterset_class = OnuFilter
    template_name = "warehouse/onu_list.html"
    htmx_template_name = "warehouse/partials/onu_rows.html"
    context_object_name = "onus"
    page_title = "ONUs"
    page_subtitle = "Serialised devices, in stock and in the field"

    sort_fields = {
        "serial": "serial",
        "model": "model",
        "cost": "purchase_price",
        "bought": "purchased_on",
        "status": "status",
        "client": "client__name",
    }

    def get_queryset(self):
        queryset = Onu.objects.select_related("client")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.apply_sort(self.filterset.qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = Onu.Status
        by_status = {
            value: Q(status=value)
            for value in (status.IN_STOCK, status.ASSIGNED, status.FAULTY, status.RETIRED)
        }

        # The fleet as a whole, whatever the search: these answer "can we do
        # the next install" and double as the status chips.
        fleet = Onu.objects.aggregate(
            total=Count("pk"),
            value=money_sum("purchase_price"),
            **{f"{key}_count": Count("pk", filter=match) for key, match in by_status.items()},
            **{
                f"{key}_value": money_sum(
                    Case(
                        When(match, then=F("purchase_price")),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                )
                for key, match in by_status.items()
            },
        )
        fleet["out_of_service"] = fleet["faulty_count"] + fleet["retired_count"]
        fleet["out_of_service_value"] = fleet["faulty_value"] + fleet["retired_value"]
        fleet["deployed_percent"] = (
            round(fleet["assigned_count"] / fleet["total"] * 100) if fleet["total"] else 0
        )
        context["fleet"] = fleet
        context["models"] = self.model_breakdown()

        context["chips"] = build_chips(
            self.request,
            "status",
            [
                {"label": "All ONUs", "value": fleet["total"], "match": None},
                {
                    "label": "In stock",
                    "value": fleet["in_stock_count"],
                    "match": status.IN_STOCK,
                    "tone": "success",
                },
                {"label": "Installed", "value": fleet["assigned_count"], "match": status.ASSIGNED},
                {
                    "label": "Faulty",
                    "value": fleet["faulty_count"],
                    "match": status.FAULTY,
                    "tone": "danger",
                },
                {
                    "label": "Retired",
                    "value": fleet["retired_count"],
                    "match": status.RETIRED,
                    "tone": "muted",
                },
            ],
        )
        context["row_noun"], context["row_noun_plural"] = "ONU", "ONUs"
        return context

    def model_breakdown(self):
        """Each model's units split by where they are, busiest model first.

        What a purchasing decision needs: which model is running out, and
        which one is failing. Each row filters the table to that model.
        """
        status = Onu.Status
        rows = list(
            Onu.objects.order_by()
            .values("model")
            .annotate(
                total=Count("pk"),
                in_stock=Count("pk", filter=Q(status=status.IN_STOCK)),
                assigned=Count("pk", filter=Q(status=status.ASSIGNED)),
                out=Count("pk", filter=Q(status__in=[status.FAULTY, status.RETIRED])),
            )
            .order_by("-total", "model")
        )
        current = self.request.GET.get("model", "")
        for row in rows:
            total = row["total"] or 1
            row["label"] = row["model"] or "Unspecified model"
            row["assigned_percent"] = row["assigned"] / total * 100
            row["in_stock_percent"] = row["in_stock"] / total * 100
            row["out_percent"] = row["out"] / total * 100
            row["is_active"] = bool(row["model"]) and row["model"] == current
            row["url"] = (
                filtered_url(self.request, model=None if row["is_active"] else row["model"])
                if row["model"]
                else ""
            )
        return rows


class OnuCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_onu"
    model = Onu
    form_class = OnuForm
    success_url = reverse_lazy("onu_list")
    success_message = "ONU %(serial)s was added."
    page_title = "Add ONU"
    page_subtitle = "A device bought into stock"
    template_name = "warehouse/onu_form.html"


class OnuUpdateView(CrudViewMixin, UpdateView):
    permission_required = "warehouse.change_onu"
    model = Onu
    form_class = OnuForm
    success_url = reverse_lazy("onu_list")
    success_message = "ONU %(serial)s was updated."
    page_title = "Edit ONU"
    template_name = "warehouse/onu_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        onu = self.object
        context["page_subtitle"] = " · ".join(filter(None, [onu.serial, onu.model]))
        return context


class OnuDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "warehouse.delete_onu"
    model = Onu
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("onu_list")
    page_title = "Delete ONU"

    def form_valid(self, form):
        onu = self.get_object()
        if onu.assigned_client:
            messages.error(
                self.request,
                f"ONU {onu.serial} is installed at {onu.assigned_client.name}. "
                "Unassign it from the client first.",
            )
            return redirect("onu_list")
        return super().form_valid(form)


# ---------------------------------------------------------------------------#
# Stock movements
# ---------------------------------------------------------------------------#


class StockMovementListView(FilteredListView):
    permission_required = "warehouse.view_stockmovement"
    model = StockMovement
    filterset_class = StockMovementFilter
    template_name = "warehouse/movement_list.html"
    context_object_name = "movements"
    page_title = "Stock movements"
    page_subtitle = "Every receipt, issue and correction"

    def get_queryset(self):
        queryset = StockMovement.objects.select_related("product", "created_by")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.filterset.qs


class StockMovementCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_stockmovement"
    model = StockMovement
    form_class = StockMovementForm
    template_name = "form.html"
    success_url = reverse_lazy("movement_list")
    success_message = "Stock movement recorded."
    page_title = "Record stock movement"
