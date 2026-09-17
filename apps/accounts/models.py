"""Customers: where they connect, what they bought, and on what terms."""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Case, DecimalField, F, Q, Value, When
from django.urls import reverse
from django.utils import timezone

from apps.core.choices import CollectionMode
from apps.core.models import (
    ActorStampedModel,
    SoftDeleteManager,
    SoftDeleteModel,
    SoftDeleteQuerySet,
    money_field,
)
from apps.core.utils import month_start

phone_validator = RegexValidator(
    r"^\+?[0-9][0-9\- ]{6,19}$",
    "Enter a valid phone number, digits only (an optional leading + is allowed).",
)


class PackageQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Package(ActorStampedModel):
    """A sellable plan. Price here is the list price.

    What a given client actually pays is frozen on their subscription, so
    re-pricing a plan never rewrites history.
    """

    name = models.CharField(max_length=80, unique=True)
    bandwidth_mbps = models.PositiveIntegerField(
        validators=[MinValueValidator(1)], help_text="Committed speed in Mbps."
    )
    ggc_mbps = models.PositiveIntegerField(
        default=0, verbose_name="GGC (Mbps)", help_text="Cached/Google Global Cache bandwidth."
    )
    fna_mbps = models.PositiveIntegerField(
        default=0, verbose_name="FNA (Mbps)", help_text="Facebook Network Appliance bandwidth."
    )
    monthly_price = money_field(validators=[MinValueValidator(0)])
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Commission for this plan. Leave blank to use the rate in billing settings.",
    )
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = PackageQuerySet.as_manager()

    class Meta:
        ordering = ["-is_active", "monthly_price", "name"]

    def __str__(self):
        return f"{self.name} — {self.bandwidth_mbps} Mbps"

    def get_absolute_url(self):
        return reverse("package_list")

    @property
    def subscriber_count(self) -> int:
        return self.subscriptions.filter(status=Subscription.Status.ACTIVE).count()


class ClientQuerySet(SoftDeleteQuerySet):
    """Client lookups. Inherits the soft-delete behaviour rather than
    replacing it — a plain `models.QuerySet` here would have made
    `Client.objects` show archived clients again."""

    def active(self):
        return self.filter(status=Client.Status.ACTIVE)

    def billable(self):
        """Clients who should receive an invoice this month."""
        return self.filter(status__in=[Client.Status.ACTIVE, Client.Status.SUSPENDED])

    def with_related(self):
        """Everything a list page needs, without a query per row.

        The outstanding balance is annotated rather than computed per client:
        as a property it cost one query per row, so a 25-row page ran 25 extra
        queries and a larger page ran proportionally more.
        """
        from apps.accountants.models import Invoice
        from apps.core.aggregates import money_sum

        return (
            self.select_related("pop", "onu")
            .prefetch_related("subscriptions__package")
            .order_by(*Client._meta.ordering)
            .annotate(
                outstanding=money_sum(
                    Case(
                        When(
                            ~Q(
                                invoices__status__in=[
                                    Invoice.Status.CANCELLED,
                                    Invoice.Status.PAID,
                                ]
                            ),
                            then=F("invoices__total") - F("invoices__amount_paid"),
                        ),
                        default=Value(Decimal("0.00")),
                        output_field=DecimalField(max_digits=14, decimal_places=2),
                    )
                )
            )
        )


class Client(SoftDeleteModel, ActorStampedModel):
    """A subscriber.

    Soft-deleted rather than removed: invoices, payments and assigned hardware
    all point here, and the books have to stay readable after someone leaves.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending install"
        ACTIVE = "active", "Active"
        SUSPENDED = "suspended", "Suspended"
        TERMINATED = "terminated", "Terminated"

    client_code = models.CharField(
        max_length=20, unique=True, editable=False, help_text="Auto-assigned, e.g. C-000123."
    )
    name = models.CharField(max_length=120, db_index=True)
    username = models.CharField(
        max_length=80,
        unique=True,
        verbose_name="Username / IP",
        help_text="The login or static IP this connection is identified by.",
    )
    phone = models.CharField(max_length=20, validators=[phone_validator], db_index=True)
    email = models.EmailField(blank=True)
    nid = models.CharField(max_length=30, blank=True, verbose_name="NID")
    address = models.CharField(max_length=255)
    pop = models.ForeignKey(
        "warehouse.Pop", on_delete=models.PROTECT, related_name="clients", verbose_name="POP"
    )
    onu = models.OneToOneField(
        "warehouse.Onu",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client",
        verbose_name="ONU",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    collection_mode = models.CharField(
        max_length=20,
        choices=CollectionMode.choices,
        blank=True,
        default="",
        db_index=True,
        help_text="Leave blank to follow the default in billing settings.",
    )
    connection_date = models.DateField(default=timezone.localdate)
    billing_day = models.PositiveSmallIntegerField(
        default=1,
        help_text="Day of month the invoice is raised (1–28).",
    )
    notes = models.TextField(blank=True)

    # `objects` hides archived clients; `all_objects` is how the admin and the
    # code-assignment logic still reach them.
    objects = SoftDeleteManager.from_queryset(ClientQuerySet)()
    all_objects = ClientQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "pop"]),
            models.Index(fields=["name"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(billing_day__gte=1) & Q(billing_day__lte=28),
                name="client_billing_day_in_range",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.username})"

    def get_absolute_url(self):
        return reverse("client_detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.client_code:
            self.client_code = self._next_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _next_code() -> str:
        last = Client.all_objects.order_by("-id").values_list("id", flat=True).first() or 0
        return f"C-{last + 1:06d}"

    @property
    def subscription(self):
        """The current subscription, or None.

        Prefetched by `ClientQuerySet.with_related`, so list pages do not pay
        a query per row for it.
        """
        for sub in self.subscriptions.all():
            if sub.status == Subscription.Status.ACTIVE:
                return sub
        return None

    @property
    def package(self):
        sub = self.subscription
        return sub.package if sub else None

    @property
    def monthly_price(self):
        sub = self.subscription
        return sub.monthly_price if sub else None

    @property
    def effective_collection_mode(self) -> str:
        """Who collects this client's bills.

        A reseller's base is usually mixed — some customers pay cash at the
        counter while others pay the upstream portal online — so the per-client
        value wins over the business-wide default when it is set.
        """
        from apps.accountants.models import BillingSettings

        return self.collection_mode or BillingSettings.load().collection_mode

    @property
    def pays_upstream_directly(self) -> bool:
        return self.effective_collection_mode == CollectionMode.UPSTREAM

    @property
    def balance_due(self):
        """Unpaid invoice total. Positive means the client owes money.

        Uses the `outstanding` annotation when the queryset supplied one
        (see `ClientQuerySet.with_related`) and falls back to querying for a
        single object fetched on its own.
        """
        annotated = getattr(self, "outstanding", None)
        if annotated is not None:
            return annotated

        from apps.accountants.models import Invoice

        rows = self.invoices.exclude(status__in=[Invoice.Status.CANCELLED, Invoice.Status.PAID])
        return sum((invoice.amount_due for invoice in rows), start=Decimal("0.00"))


class SubscriptionQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Subscription.Status.ACTIVE)


class Subscription(ActorStampedModel):
    """What a client is on, and what they pay for it.

    `monthly_price` is copied from the package at sign-up. Changing a plan's
    price later moves new subscriptions only — existing customers keep the
    terms they agreed to until someone changes them deliberately.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="subscriptions")
    package = models.ForeignKey(Package, on_delete=models.PROTECT, related_name="subscriptions")
    monthly_price = money_field()
    discount = money_field(help_text="Flat monthly discount applied to this client.")
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Commission agreed for this client. Blank falls back to the package, then settings.",
    )
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        ordering = ["-start_date", "-id"]
        constraints = [
            # One live subscription per client; history is kept as cancelled rows.
            models.UniqueConstraint(
                fields=["client"],
                condition=Q(status="active"),
                name="one_active_subscription_per_client",
            ),
        ]

    def __str__(self):
        return f"{self.client.name} → {self.package.name}"

    @property
    def net_monthly(self):
        return max(self.monthly_price - self.discount, 0)

    @property
    def effective_commission_percent(self):
        """Resolve the commission rate: subscription, then package, then settings.

        Upstream operators commonly pay a different rate per plan tier, and
        occasionally a negotiated one for a single large customer, so all three
        levels are real rather than speculative.
        """
        from apps.accountants.models import BillingSettings

        if self.commission_percent is not None:
            return self.commission_percent
        if self.package.commission_percent is not None:
            return self.package.commission_percent
        return BillingSettings.load().commission_percent

    def cancel(self, when=None):
        self.status = self.Status.CANCELLED
        self.end_date = when or timezone.localdate()
        self.save(update_fields=["status", "end_date", "updated_at"])

    def covers(self, period) -> bool:
        """Is this subscription live during the given billing month?"""
        period = month_start(period)
        if self.start_date and month_start(self.start_date) > period:
            return False
        if self.end_date and month_start(self.end_date) < period:
            return False
        return True
