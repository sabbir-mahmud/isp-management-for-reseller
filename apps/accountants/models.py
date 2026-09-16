"""Billing and the books.

The old design inferred revenue as "sum of every active client's package
price". That is a forecast, not a fact — it cannot express a partial payment,
an arrear, a mid-month join or a discount. Here an `Invoice` is what was
billed, a `Payment` is what arrived, and the difference is what is owed.
"""

from decimal import Decimal

from django.core.cache import cache
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.core.choices import CollectionMode
from apps.core.models import ActorStampedModel, money_field
from apps.core.utils import month_start, split_commission


class BillingSettings(ActorStampedModel):
    """Single-row configuration for the billing engine.

    A singleton by construction (`pk=1`); `load()` is the only supported way
    to read it, so a fresh install cannot 500 on a missing row.
    """

    collection_mode = models.CharField(
        max_length=20,
        choices=CollectionMode.choices,
        default=CollectionMode.RESELLER,
        help_text="The default settlement arrangement. Individual clients can override it.",
    )
    upstream_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="The upstream operator's name, shown on settlement screens.",
    )
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="The reseller's share of collected bills; the rest goes upstream.",
    )
    invoice_prefix = models.CharField(max_length=10, default="INV")
    due_days = models.PositiveSmallIntegerField(
        default=10, help_text="Days after issue before an invoice is overdue."
    )
    auto_generate = models.BooleanField(
        default=True, help_text="Let the monthly job raise invoices automatically."
    )

    class Meta:
        verbose_name = "billing settings"
        verbose_name_plural = "billing settings"
        permissions = [
            ("view_dashboard", "Can view the business dashboard"),
            ("view_financial_report", "Can view financial reports"),
            ("export_data", "Can export data to CSV"),
        ]

    def __str__(self):
        return f"{self.get_collection_mode_display()} at {self.commission_percent}%"

    #: Cache key for the singleton. Read on nearly every page — and once per
    #: row wherever a client's effective collection mode is shown — so an
    #: uncached `load()` turns a 25-row list into 25 extra queries.
    CACHE_KEY = "billing-settings"
    CACHE_TTL = 300

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)

    def delete(self, *args, **kwargs):
        cache.delete(self.CACHE_KEY)
        return super().delete(*args, **kwargs)

    @classmethod
    def load(cls) -> BillingSettings:
        row = cache.get(cls.CACHE_KEY)
        if row is None:
            row, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls.CACHE_KEY, row, cls.CACHE_TTL)
        return row


class InvoiceQuerySet(models.QuerySet):
    def outstanding(self):
        return self.filter(
            status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIAL, Invoice.Status.OVERDUE]
        )

    def for_period(self, period):
        return self.filter(period=month_start(period))

    def with_related(self):
        return self.select_related("client", "subscription__package")


class Invoice(ActorStampedModel):
    """One month's bill for one client."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        UNPAID = "unpaid", "Unpaid"
        PARTIAL = "partial", "Partially paid"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(max_length=32, unique=True, editable=False)
    client = models.ForeignKey("accounts.Client", on_delete=models.PROTECT, related_name="invoices")
    subscription = models.ForeignKey(
        "accounts.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    period = models.DateField(
        db_index=True, help_text="The billing month, stored as its first day."
    )
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    subtotal = money_field()
    discount = money_field()
    total = money_field(editable=False)
    amount_paid = money_field(editable=False)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UNPAID, db_index=True
    )
    # Snapshots, not lookups. Switching the business to a different settlement
    # arrangement (or renegotiating the rate) must not silently restate what
    # last quarter's invoices were worth.
    collection_mode = models.CharField(
        max_length=20,
        choices=CollectionMode.choices,
        default=CollectionMode.RESELLER,
        db_index=True,
        help_text="Who collects this bill. Fixed when the invoice is raised.",
    )
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    commission_amount = money_field(editable=False, help_text="The reseller's share of this bill.")
    upstream_amount = money_field(editable=False, help_text="The upstream operator's share.")
    note = models.CharField(max_length=255, blank=True)

    objects = InvoiceQuerySet.as_manager()

    class Meta:
        ordering = ["-period", "-id"]
        indexes = [
            models.Index(fields=["status", "period"]),
            models.Index(fields=["client", "-period"]),
        ]
        constraints = [
            # The monthly job is safe to re-run: one bill per client per month.
            models.UniqueConstraint(
                fields=["client", "period"],
                condition=~Q(status="cancelled"),
                name="one_invoice_per_client_per_period",
            ),
        ]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse("invoice_detail", args=[self.pk])

    def save(self, *args, **kwargs):
        self.period = month_start(self.period)
        self.total = max(self.subtotal - self.discount, Decimal("0.00"))
        self.commission_amount, self.upstream_amount = split_commission(
            self.total, self.commission_percent
        )
        if not self.number:
            self.number = self._next_number()
        super().save(*args, **kwargs)

    def _next_number(self) -> str:
        settings_row = BillingSettings.load()
        period = month_start(self.period)
        stamp = period.strftime("%Y%m")
        prefix = f"{settings_row.invoice_prefix}-{stamp}-"
        last = (
            Invoice.objects.filter(number__startswith=prefix)
            .order_by("-number")
            .values_list("number", flat=True)
            .first()
        )
        sequence = int(last.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{sequence:04d}"

    @property
    def amount_due(self) -> Decimal:
        """What the customer still owes — whoever is collecting it."""
        return max(self.total - self.amount_paid, Decimal("0.00"))

    @property
    def collected_by_reseller(self) -> bool:
        return self.collection_mode == CollectionMode.RESELLER

    @property
    def payee(self) -> str:
        """Who the customer should pay, for the UI to say so plainly."""
        if self.collected_by_reseller:
            return "you"
        return BillingSettings.load().upstream_name or "the upstream operator"

    @property
    def is_overdue(self) -> bool:
        return self.amount_due > 0 and self.due_date < timezone.localdate()

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_date).days

    @transaction.atomic
    def recalculate(self, save: bool = True) -> Invoice:
        """Re-derive totals and status from the lines and payments."""
        lines_total = self.lines.aggregate(total=Sum("line_total"))["total"]
        if lines_total is not None:
            self.subtotal = lines_total
        self.total = max(self.subtotal - self.discount, Decimal("0.00"))
        self.commission_amount, self.upstream_amount = split_commission(
            self.total, self.commission_percent
        )
        self.amount_paid = self.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

        if self.status != self.Status.CANCELLED:
            if self.amount_paid >= self.total and self.total > 0:
                self.status = self.Status.PAID
            elif self.amount_paid > 0:
                self.status = self.Status.PARTIAL
            elif self.due_date < timezone.localdate():
                self.status = self.Status.OVERDUE
            else:
                self.status = self.Status.UNPAID

        if save:
            super().save(
                update_fields=[
                    "subtotal",
                    "total",
                    "commission_amount",
                    "upstream_amount",
                    "amount_paid",
                    "status",
                    "updated_at",
                ]
            )
        return self


class InvoiceLine(models.Model):
    """A charge on an invoice. Monthly fee, installation, equipment, penalty."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1.00"))
    unit_price = money_field()
    line_total = money_field(editable=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.description

    def save(self, *args, **kwargs):
        self.line_total = (self.quantity * self.unit_price).quantize(Decimal("0.01"))
        super().save(*args, **kwargs)
        self.invoice.recalculate()


class Payment(ActorStampedModel):
    """A customer payment against an invoice.

    Under `RESELLER` collection this is cash the reseller now holds. Under
    `UPSTREAM` collection the customer paid the upstream operator directly and
    the reseller never touched the money — the row is a reconciliation of the
    upstream statement, and what it earns the reseller is `commission_amount`.

    `collection_mode` and `commission_amount` are copied from the invoice on
    save so cash-position queries never have to join back through it.
    """

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BKASH = "bkash", "bKash"
        NAGAD = "nagad", "Nagad"
        ROCKET = "rocket", "Rocket"
        BANK = "bank", "Bank transfer"
        ONLINE = "online", "Online (upstream portal)"
        OTHER = "other", "Other"

    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    client = models.ForeignKey(
        "accounts.Client", on_delete=models.PROTECT, related_name="payments", editable=False
    )
    amount = money_field(validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    received_on = models.DateField(default=timezone.localdate, db_index=True)
    reference = models.CharField(
        max_length=80, blank=True, help_text="Transaction ID or receipt number."
    )
    collection_mode = models.CharField(
        max_length=20,
        choices=CollectionMode.choices,
        default=CollectionMode.RESELLER,
        editable=False,
        db_index=True,
    )
    commission_amount = money_field(
        editable=False, help_text="What the reseller earns from this payment."
    )
    upstream_amount = money_field(
        editable=False, help_text="The upstream operator's share of this payment."
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-received_on", "-id"]
        indexes = [
            models.Index(fields=["received_on"]),
            models.Index(fields=["collection_mode", "received_on"]),
        ]

    def __str__(self):
        return f"{self.amount} via {self.get_method_display()}"

    def save(self, *args, **kwargs):
        # Denormalised so collection reports never need to join through invoices.
        self.client_id = self.invoice.client_id
        self.collection_mode = self.invoice.collection_mode
        # Commission is split per payment, not per invoice, so a half payment
        # earns half the commission instead of the whole of it up front.
        self.commission_amount, self.upstream_amount = split_commission(
            self.amount, self.invoice.commission_percent
        )
        super().save(*args, **kwargs)
        self.invoice.recalculate()

    @property
    def is_reseller_cash(self) -> bool:
        """Did this money actually reach the reseller?"""
        return self.collection_mode == CollectionMode.RESELLER

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        result = super().delete(*args, **kwargs)
        invoice.recalculate()
        return result


class UpstreamSettlement(ActorStampedModel):
    """Money moving between the reseller and the upstream operator.

    The direction depends on the arrangement, and both directions are real
    business events that were previously invisible:

    * `REMITTANCE` — the reseller pays the upstream operator their share of
      what was collected from customers (the `RESELLER` arrangement).
    * `COMMISSION_PAYOUT` — the upstream operator pays the reseller the
      commission earned on bills customers paid directly (the `UPSTREAM`
      arrangement).

    A remittance is deliberately **not** an `Expense`. The upstream share was
    never the reseller's revenue, so recording it as a cost as well would
    deduct the same money twice.
    """

    class Kind(models.TextChoices):
        REMITTANCE = "remittance", "Paid to upstream"
        COMMISSION_PAYOUT = "commission_payout", "Commission received from upstream"

    kind = models.CharField(max_length=30, choices=Kind.choices, db_index=True)
    amount = money_field(validators=[MinValueValidator(Decimal("0.01"))])
    period = models.DateField(
        db_index=True, help_text="The month being settled, stored as its first day."
    )
    settled_on = models.DateField(default=timezone.localdate, db_index=True)
    reference = models.CharField(
        max_length=80, blank=True, help_text="Bank reference or statement number."
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-settled_on", "-id"]
        indexes = [models.Index(fields=["kind", "period"])]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.amount} ({self.period:%b %Y})"

    def get_absolute_url(self):
        return reverse("settlement_list")

    def save(self, *args, **kwargs):
        self.period = month_start(self.period)
        super().save(*args, **kwargs)

    @property
    def is_outgoing(self) -> bool:
        return self.kind == self.Kind.REMITTANCE


class LedgerEntry(ActorStampedModel):
    """Shared shape for the two manual ledgers below."""

    description = models.CharField(max_length=250)
    amount = money_field(validators=[MinValueValidator(Decimal("0.01"))])
    occurred_on = models.DateField(default=timezone.localdate, db_index=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True
        ordering = ["-occurred_on", "-id"]

    def __str__(self):
        return self.description

    @property
    def period(self):
        return month_start(self.occurred_on)


class Expense(LedgerEntry):
    """Money out: upstream bandwidth bills, salaries, fuel, hardware purchases.

    Was `Invest`, whose month/year were free-text lookup rows; the date is now
    a real column the database can group and range over.
    """

    class Category(models.TextChoices):
        BANDWIDTH = "bandwidth", "Upstream bandwidth"
        SALARY = "salary", "Salary"
        EQUIPMENT = "equipment", "Equipment"
        MAINTENANCE = "maintenance", "Maintenance"
        RENT = "rent", "Rent & utilities"
        OTHER = "other", "Other"

    category = models.CharField(
        max_length=20, choices=Category.choices, default=Category.OTHER, db_index=True
    )

    class Meta(LedgerEntry.Meta):
        abstract = False
        ordering = ["-occurred_on", "-id"]

    def get_absolute_url(self):
        return reverse("expense_list")


class Income(LedgerEntry):
    """Money in that is not a subscription payment: installations, sales, repairs.

    Subscription revenue lives in `Payment` and is never entered here, so the
    two can be added together without double counting.
    """

    class Source(models.TextChoices):
        INSTALLATION = "installation", "Installation fee"
        HARDWARE = "hardware", "Hardware sale"
        SERVICE = "service", "Service & repair"
        OTHER = "other", "Other"

    source = models.CharField(
        max_length=20, choices=Source.choices, default=Source.OTHER, db_index=True
    )

    class Meta(LedgerEntry.Meta):
        abstract = False
        ordering = ["-occurred_on", "-id"]

    def get_absolute_url(self):
        return reverse("income_list")
