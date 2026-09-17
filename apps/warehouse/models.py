"""Inventory: stock the reseller holds, and the ONUs sitting in customer homes."""

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.models import ActorStampedModel, money_field


class Pop(ActorStampedModel):
    """A point of presence — the physical node a client hangs off.

    Self-referencing so a sub-POP can name its upstream. `SET_NULL` rather
    than the original `CASCADE`: retiring an upstream POP must not delete the
    downstream ones and, transitively, their clients.
    """

    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, blank=True, help_text="Short label used on reports.")
    address = models.CharField(max_length=255, blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="upstream POP",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "POP"
        verbose_name_plural = "POPs"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("pop_list")

    @property
    def active_client_count(self) -> int:
        return self.clients.filter(status="active").count()


class Category(ActorStampedModel):
    name = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def in_stock(self):
        return self.filter(quantity__gt=0)

    def low_stock(self):
        return self.filter(quantity__lte=models.F("reorder_level"))


class Product(ActorStampedModel):
    """A consumable or spare held in stock, counted by quantity.

    Quantity is never edited directly by the UI — it is the running total of
    `StockMovement` rows, so every change has a reason and an author.
    """

    class Status(models.TextChoices):
        IN_STOCK = "in_stock", "In stock"
        RESERVED = "reserved", "Reserved"
        RETIRED = "retired", "Retired"

    name = models.CharField(max_length=160, db_index=True)
    model = models.CharField(max_length=120, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    quantity = models.IntegerField(default=0, editable=False)
    reorder_level = models.PositiveIntegerField(
        default=0, help_text="Flag the item once stock falls to this level."
    )
    unit_price = money_field(validators=[MinValueValidator(0)])
    sku = models.CharField(max_length=80, blank=True, verbose_name="SKU / serial")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_STOCK)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # Blank SKUs are common for bulk items, so only non-empty ones are
            # forced unique — a plain `unique=True` would allow exactly one.
            models.UniqueConstraint(
                fields=["sku"], condition=~Q(sku=""), name="product_sku_unique_when_set"
            ),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("product_list")

    @property
    def stock_value(self):
        return self.quantity * self.unit_price

    @property
    def is_low(self) -> bool:
        return self.quantity <= self.reorder_level

    def recalculate_quantity(self, save: bool = True) -> int:
        """Re-derive quantity from the movement ledger."""
        total = (
            self.movements.aggregate(total=Sum("quantity", filter=Q(kind=StockMovement.Kind.IN)))[
                "total"
            ]
            or 0
        )
        out = (
            self.movements.aggregate(total=Sum("quantity", filter=Q(kind=StockMovement.Kind.OUT)))[
                "total"
            ]
            or 0
        )
        adjust = (
            self.movements.aggregate(
                total=Sum("quantity", filter=Q(kind=StockMovement.Kind.ADJUST))
            )["total"]
            or 0
        )
        self.quantity = total - out + adjust
        if save:
            Product.objects.filter(pk=self.pk).update(quantity=self.quantity)
        return self.quantity


class StockMovement(ActorStampedModel):
    """Every stock change, with a reason. The product quantity is its sum."""

    class Kind(models.TextChoices):
        IN = "in", "Received"
        OUT = "out", "Issued"
        ADJUST = "adjust", "Adjustment"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    quantity = models.IntegerField(help_text="Signed only for adjustments; otherwise positive.")
    reason = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=80, blank=True)
    occurred_on = models.DateField(default=timezone.localdate)

    class Meta:
        ordering = ["-occurred_on", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.quantity} × {self.product.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.product.recalculate_quantity()


class OnuQuerySet(models.QuerySet):
    def available(self):
        return self.filter(status=Onu.Status.IN_STOCK)


class Onu(ActorStampedModel):
    """A serialised ONU. Unlike `Product`, each unit is tracked individually.

    Status follows assignment: handing one to a client marks it assigned, and
    unassigning returns it to stock (see `apps.accounts.services`).
    """

    class Status(models.TextChoices):
        IN_STOCK = "in_stock", "In stock"
        ASSIGNED = "assigned", "Assigned"
        FAULTY = "faulty", "Faulty"
        RETIRED = "retired", "Retired"

    serial = models.CharField(max_length=120, unique=True, db_index=True)
    name = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    port = models.PositiveSmallIntegerField(default=1)
    purchase_price = money_field(validators=[MinValueValidator(0)])
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.IN_STOCK, db_index=True
    )
    purchased_on = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=255, blank=True)

    objects = OnuQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ONU"
        verbose_name_plural = "ONUs"

    def __str__(self):
        return self.serial

    def get_absolute_url(self):
        return reverse("onu_list")

    @property
    def assigned_client(self):
        return getattr(self, "client", None)
