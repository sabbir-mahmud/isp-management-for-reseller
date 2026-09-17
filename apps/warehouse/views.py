"""Inventory screens: stock, serialised ONUs and the movement ledger."""

from django.contrib import messages
from django.db.models import (
    Case,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
    Value,
    When,
)
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from apps.accounts.views import FilteredListView
from apps.core.aggregates import money_sum
from apps.core.chips import build_chips
from apps.core.mixins import CrudViewMixin, PageTitleMixin, SortableListMixin, StaffViewMixin
from apps.core.utils import filtered_url

from .filters import OnuFilter, ProductFilter, StockMovementFilter
from .forms import CategoryForm, OnuForm, ProductForm, StockMovementForm
from .models import Category, Onu, Product, StockMovement


class ProductListView(SortableListMixin, FilteredListView):
    permission_required = "warehouse.view_product"
    model = Product
    filterset_class = ProductFilter
    template_name = "warehouse/product_list.html"
    htmx_template_name = "warehouse/partials/product_rows.html"
    context_object_name = "products"
    page_title = "Stock"
    page_subtitle = "Cables, routers, spares — what is on the shelf"

    sort_fields = {
        "name": "name",
        "category": "category__name",
        "quantity": "quantity",
        "price": "unit_price",
        "value": "value",
    }

    def get_queryset(self):
        queryset = Product.objects.select_related("category").annotate(value=STOCK_VALUE)
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.apply_sort(self.filterset.qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        levels = {key: ProductFilter.level_q(key) for key, _ in ProductFilter.LEVEL_CHOICES}
        # The whole shelf, whatever the search: these answer "what needs
        # ordering" and double as the stock-level chips.
        totals = Product.objects.aggregate(
            skus=Count("pk"),
            units=Sum("quantity", default=Value(0)),
            value=money_sum(STOCK_VALUE),
            categories=Count("category", distinct=True),
            **{key: Count("pk", filter=match) for key, match in levels.items()},
        )
        context["totals"] = totals
        context["reorder"] = list(
            Product.objects.filter(levels["low"] | levels["out"])
            .exclude(status=Product.Status.RETIRED)
            .order_by("quantity", "name")
            .values("name", "quantity")[:6]
        )
        context["chips"] = build_chips(
            self.request,
            "level",
            [
                {"label": "All items", "value": totals["skus"], "match": None},
                {
                    "label": "Healthy",
                    "value": totals["healthy"],
                    "match": "healthy",
                    "tone": "success",
                },
                {
                    "label": "Running low",
                    "value": totals["low"],
                    "match": "low",
                    "tone": "warning",
                },
                {"label": "Out of stock", "value": totals["out"], "match": "out", "tone": "danger"},
            ],
        )
        context["chip_group"] = "stock level"
        context["row_noun"], context["row_noun_plural"] = "item", "items"
        return context


#: What a product's stock is worth at its unit price.
STOCK_VALUE = ExpressionWrapper(
    F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=14, decimal_places=2)
)


class ProductCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_product"
    model = Product
    form_class = ProductForm
    template_name = "form.html"
    success_url = reverse_lazy("product_list")
    success_message = "%(name)s was added to stock."
    page_title = "Add stock item"
    page_subtitle = "Something you keep on the shelf and count by the unit"

    def get_initial(self):
        category = self.request.GET.get("category", "")
        return {"category": category} if category.isdigit() else {}

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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object
        context["page_subtitle"] = f"{product.name} · {product.quantity} on hand"
        context["notice"] = (
            "The quantity is not edited here. Record a movement to receive, issue or "
            "correct stock, so every change keeps its reason."
        )
        return context


class ProductDeleteView(StaffViewMixin, PageTitleMixin, DeleteView):
    permission_required = "warehouse.delete_product"
    model = Product
    template_name = "confirm_delete.html"
    success_url = reverse_lazy("product_list")
    page_title = "Delete stock item"


# ---------------------------------------------------------------------------#
# Categories
# ---------------------------------------------------------------------------#


class CategoryListView(StaffViewMixin, PageTitleMixin, SortableListMixin, ListView):
    permission_required = "warehouse.view_category"
    model = Category
    template_name = "warehouse/category_list.html"
    context_object_name = "categories"
    paginate_by = 50
    page_title = "Categories"
    page_subtitle = "How the shelf is grouped, and what each group holds"

    sort_fields = {
        "name": "name",
        "items": "products_count",
        "units": "units",
        "value": "value",
    }
    default_sort = "name"

    def get_queryset(self):
        queryset = Category.objects.annotate(
            products_count=Count("products"),
            units=Sum("products__quantity", default=Value(0)),
            value=money_sum(
                ExpressionWrapper(
                    F("products__quantity") * F("products__unit_price"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            attention=Count(
                "products",
                filter=Q(products__quantity__lte=F("products__reorder_level"))
                & ~Q(products__status=Product.Status.RETIRED),
            ),
        )
        return self.apply_sort(queryset)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Distinct: the filter joins products, one row per product.
        totals = Category.objects.aggregate(
            count=Count("pk", distinct=True),
            empty=Count("pk", filter=Q(products__isnull=True), distinct=True),
        )
        totals["value"] = Product.objects.aggregate(value=money_sum(STOCK_VALUE))["value"]
        totals["items"] = Product.objects.count()
        context["totals"] = totals
        grand = totals["value"] or 0
        for category in context["categories"]:
            category.share = round(category.value / grand * 100) if grand else 0
        return context


class CategoryCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_category"
    model = Category
    form_class = CategoryForm
    template_name = "warehouse/category_form.html"
    success_url = reverse_lazy("category_list")
    success_message = "Category %(name)s was created."
    page_title = "Add category"
    page_subtitle = "A group for the stock page and its filters"

    #: The value of the secondary submit button that goes on to add an item.
    THEN_ADD_ITEM = "add_item"

    def get_success_url(self):
        if self.request.POST.get("then") == self.THEN_ADD_ITEM:
            return f"{reverse('product_add')}?category={self.object.pk}"
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_label"] = "Create category"
        context["then_add_item"] = (
            self.THEN_ADD_ITEM if self.request.user.has_perm("warehouse.add_product") else ""
        )
        return context


class CategoryUpdateView(CrudViewMixin, UpdateView):
    permission_required = "warehouse.change_category"
    model = Category
    form_class = CategoryForm
    template_name = "warehouse/category_form.html"
    success_url = reverse_lazy("category_list")
    success_message = "Category %(name)s was updated."
    page_title = "Edit category"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.object
        context["page_subtitle"] = category.name
        context["submit_label"] = "Save changes"
        # What the category holds, so a rename is made knowing what it moves.
        products = category.products.all()
        holdings = products.aggregate(
            items=Count("pk"),
            units=Sum("quantity", default=Value(0)),
            value=money_sum(STOCK_VALUE),
            to_reorder=Count(
                "pk",
                filter=Q(quantity__lte=F("reorder_level")) & ~Q(status=Product.Status.RETIRED),
            ),
        )
        holdings["sample"] = list(products.order_by("name").values_list("name", flat=True)[:4])
        holdings["more"] = holdings["items"] - len(holdings["sample"])
        context["holdings"] = holdings
        return context


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


class StockMovementListView(SortableListMixin, FilteredListView):
    permission_required = "warehouse.view_stockmovement"
    model = StockMovement
    filterset_class = StockMovementFilter
    template_name = "warehouse/movement_list.html"
    htmx_template_name = "warehouse/partials/movement_rows.html"
    context_object_name = "movements"
    page_title = "Stock movements"
    page_subtitle = "Every receipt, issue and correction"

    sort_fields = {"date": "occurred_on", "item": "product__name", "quantity": "quantity"}

    def get_queryset(self):
        queryset = StockMovement.objects.select_related("product", "created_by")
        self.filterset = self.filterset_class(self.request.GET, queryset=queryset)
        return self.apply_sort(self.filterset.qs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        kind = StockMovement.Kind
        totals = self.filterset.qs.aggregate(
            count=Count("pk"),
            received=Sum("quantity", filter=Q(kind=kind.IN), default=Value(0)),
            issued=Sum("quantity", filter=Q(kind=kind.OUT), default=Value(0)),
            adjusted=Sum("quantity", filter=Q(kind=kind.ADJUST), default=Value(0)),
            items=Count("product", distinct=True),
        )
        totals["net"] = totals["received"] - totals["issued"] + totals["adjusted"]
        context["totals"] = totals

        counts = StockMovement.objects.aggregate(
            all=Count("pk"),
            **{value: Count("pk", filter=Q(kind=value)) for value in kind.values},
        )
        context["chips"] = build_chips(
            self.request,
            "kind",
            [
                {"label": "All movements", "value": counts["all"], "match": None},
                {
                    "label": "Received",
                    "value": counts[kind.IN],
                    "match": kind.IN,
                    "tone": "success",
                },
                {
                    "label": "Issued",
                    "value": counts[kind.OUT],
                    "match": kind.OUT,
                    "tone": "warning",
                },
                {
                    "label": "Adjustments",
                    "value": counts[kind.ADJUST],
                    "match": kind.ADJUST,
                    "tone": "muted",
                },
            ],
        )
        context["chip_group"] = "movement type"
        context["row_noun"], context["row_noun_plural"] = "movement", "movements"
        return context


class StockMovementCreateView(CrudViewMixin, CreateView):
    permission_required = "warehouse.add_stockmovement"
    model = StockMovement
    form_class = StockMovementForm
    template_name = "warehouse/movement_form.html"
    success_url = reverse_lazy("movement_list")
    success_message = "Stock movement recorded."
    page_title = "Record stock movement"
    page_subtitle = "Stock in, stock out, or a corrected count"
    cancel_url = reverse_lazy("movement_list")

    def get_initial(self):
        """Pre-filled from the Receive / Issue links on the stock page."""
        params = self.request.GET
        initial = {"occurred_on": timezone.localdate()}
        if params.get("kind") in StockMovement.Kind.values:
            initial["kind"] = params["kind"]
        if params.get("product", "").isdigit():
            initial["product"] = int(params["product"])
        return initial

    def get_success_url(self):
        # Opened from the stock page, go back there to see the new count.
        if self.request.GET.get("next") == "stock":
            return reverse("product_list")
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["submit_label"] = "Record movement"
        # On-hand counts for the live preview under the quantity.
        context["stock_levels"] = {
            str(pk): {"quantity": quantity, "reorder": reorder}
            for pk, quantity, reorder in Product.objects.values_list(
                "pk", "quantity", "reorder_level"
            )
        }
        return context
