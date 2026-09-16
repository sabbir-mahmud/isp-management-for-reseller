"""Billing operations.

Views and management commands call these; they never write billing rows
directly. That keeps one implementation of "what does it mean to bill a
month" and makes the rules testable without a request.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import Client, Subscription
from apps.core.choices import CollectionMode
from apps.core.utils import month_end, month_start, split_commission

from .models import BillingSettings, Invoice, InvoiceLine, Payment, UpstreamSettlement

logger = logging.getLogger(__name__)


class BillingError(Exception):
    """Raised when an operation would corrupt the books."""


@dataclass
class GenerationResult:
    period: date
    created: list[Invoice] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)

    @property
    def created_count(self) -> int:
        return len(self.created)

    @property
    def billed_total(self) -> Decimal:
        return sum((inv.total for inv in self.created), start=Decimal("0.00"))

    @property
    def commission_total(self) -> Decimal:
        """What this batch earns the reseller, across both arrangements."""
        return sum((inv.commission_amount for inv in self.created), start=Decimal("0.00"))

    @property
    def reseller_collected(self) -> list[Invoice]:
        """Invoices the reseller has to collect themselves."""
        return [inv for inv in self.created if inv.collection_mode == CollectionMode.RESELLER]

    @property
    def upstream_collected(self) -> list[Invoice]:
        """Invoices the customer pays the upstream operator directly."""
        return [inv for inv in self.created if inv.collection_mode == CollectionMode.UPSTREAM]

    @property
    def to_collect_total(self) -> Decimal:
        """Cash the reseller must actually go and collect this month."""
        return sum((inv.total for inv in self.reseller_collected), start=Decimal("0.00"))

    def __str__(self):
        return (
            f"{self.period:%B %Y}: {self.created_count} invoice(s) raised "
            f"({len(self.reseller_collected)} to collect, "
            f"{len(self.upstream_collected)} paid upstream), "
            f"{len(self.skipped)} skipped"
        )


@transaction.atomic
def generate_invoices(
    period: date | None = None, *, dry_run: bool = False, actor=None
) -> GenerationResult:
    """Raise this month's invoice for every billable client.

    Idempotent: a client who already has a non-cancelled invoice for the
    period is skipped, so the monthly job can be re-run after a partial
    failure without double-billing anyone.
    """
    period = month_start(period)
    settings_row = BillingSettings.load()
    result = GenerationResult(period=period)

    existing = set(
        Invoice.objects.for_period(period)
        .exclude(status=Invoice.Status.CANCELLED)
        .values_list("client_id", flat=True)
    )

    clients = (
        Client.objects.billable().prefetch_related("subscriptions__package").order_by("client_code")
    )

    for client in clients:
        if client.pk in existing:
            result.skipped.append((client.client_code, "already invoiced"))
            continue

        subscription = client.subscription
        if subscription is None:
            result.skipped.append((client.client_code, "no active subscription"))
            continue
        if not subscription.covers(period):
            result.skipped.append((client.client_code, "subscription not active in period"))
            continue
        if subscription.net_monthly <= 0:
            result.skipped.append((client.client_code, "nothing to bill"))
            continue

        issue_date = _issue_date(period, client.billing_day)
        # Both are resolved per client, not per run: the business default can
        # be overridden on a client, and the rate on the plan or the client.
        mode = client.collection_mode or settings_row.collection_mode
        commission_percent = subscription.effective_commission_percent

        invoice = Invoice(
            client=client,
            subscription=subscription,
            period=period,
            issue_date=issue_date,
            due_date=issue_date + timedelta(days=settings_row.due_days),
            subtotal=subscription.monthly_price,
            discount=subscription.discount,
            collection_mode=mode,
            commission_percent=commission_percent,
            created_by=actor,
        )
        if dry_run:
            invoice.total = max(invoice.subtotal - invoice.discount, Decimal("0.00"))
            invoice.commission_amount, invoice.upstream_amount = split_commission(
                invoice.total, commission_percent
            )
            result.created.append(invoice)
            continue

        invoice.save()
        InvoiceLine.objects.create(
            invoice=invoice,
            description=f"{subscription.package.name} — {period:%B %Y}",
            quantity=Decimal("1.00"),
            unit_price=subscription.monthly_price,
        )
        invoice.refresh_from_db()
        result.created.append(invoice)

    if dry_run:
        transaction.set_rollback(True)
    logger.info("invoice generation %s", result)
    return result


def _issue_date(period: date, billing_day: int) -> date:
    """The client's billing day inside the period (clamped to 1–28 by the model)."""
    return period.replace(day=min(max(billing_day, 1), 28))


@transaction.atomic
def record_payment(
    invoice: Invoice,
    amount: Decimal,
    *,
    method: str = Payment.Method.CASH,
    received_on: date | None = None,
    reference: str = "",
    actor=None,
) -> Payment:
    """Take money against an invoice, refusing anything that makes no sense."""
    amount = Decimal(amount)
    if amount <= 0:
        raise BillingError("A payment must be greater than zero.")
    if invoice.status == Invoice.Status.CANCELLED:
        raise BillingError("This invoice was cancelled; it cannot take a payment.")

    invoice.recalculate()
    if amount > invoice.amount_due:
        raise BillingError(
            f"Payment of {amount} is more than the {invoice.amount_due} outstanding."
        )

    return Payment.objects.create(
        invoice=invoice,
        amount=amount,
        method=method,
        received_on=received_on or invoice.issue_date,
        reference=reference,
        created_by=actor,
    )


@transaction.atomic
def cancel_invoice(invoice: Invoice, *, actor=None) -> Invoice:
    if invoice.payments.exists():
        raise BillingError("Refund the payments before cancelling this invoice.")
    invoice.status = Invoice.Status.CANCELLED
    invoice.updated_by = actor
    invoice.save(update_fields=["status", "updated_by", "updated_at"])
    return invoice


def refresh_overdue(today: date | None = None) -> int:
    """Flip unpaid invoices past their due date to `overdue`.

    Runs from the daily job; status is stored rather than computed so the
    dashboard can filter and index on it.
    """
    today = today or timezone.localdate()
    return (
        Invoice.objects.filter(
            status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIAL], due_date__lt=today
        )
        .exclude(status=Invoice.Status.CANCELLED)
        .update(status=Invoice.Status.OVERDUE)
    )


# ---------------------------------------------------------------------------#
# Settlement with the upstream operator
# ---------------------------------------------------------------------------#


def upstream_position(period: date | None = None) -> dict:
    """What the reseller and the upstream operator owe each other.

    Two independent running balances, because they arise from opposite
    arrangements and settle separately:

    * **payable** — customers paid the reseller, and the upstream share of
      that money has not been remitted yet. The reseller is holding money
      that is not theirs.
    * **receivable** — customers paid the upstream operator directly, and the
      commission earned on those payments has not been paid across yet.

    Passing a period scopes both to that month; omitting it gives the
    all-time position, which is the number that matters for "are we square".
    """
    payments = Payment.objects.all()
    settlements = UpstreamSettlement.objects.all()
    if period is not None:
        period = month_start(period)
        window = (period, month_end(period))
        payments = payments.filter(received_on__range=window)
        settlements = settlements.filter(period=period)

    owed_upstream = _total(
        payments.filter(collection_mode=CollectionMode.RESELLER), "upstream_amount"
    )
    remitted = _total(settlements.filter(kind=UpstreamSettlement.Kind.REMITTANCE), "amount")
    commission_earned_upstream = _total(
        payments.filter(collection_mode=CollectionMode.UPSTREAM), "commission_amount"
    )
    commission_received = _total(
        settlements.filter(kind=UpstreamSettlement.Kind.COMMISSION_PAYOUT), "amount"
    )

    return {
        "period": period,
        "owed_upstream": owed_upstream,
        "remitted": remitted,
        "payable": owed_upstream - remitted,
        "commission_earned_upstream": commission_earned_upstream,
        "commission_received": commission_received,
        "receivable": commission_earned_upstream - commission_received,
    }


def _total(queryset, field) -> Decimal:
    """Sum a money column, always to the paisa.

    SQLite sums DecimalFields through a float, so a few thousand rows come
    back as 142958.120000000; quantising keeps the figure identical on both
    backends and stops that reaching a template or a comparison.
    """
    total = queryset.aggregate(total=Sum(field))["total"] or Decimal("0.00")
    return Decimal(total).quantize(Decimal("0.01"))


@transaction.atomic
def record_settlement(
    kind: str,
    amount: Decimal,
    *,
    period: date | None = None,
    settled_on: date | None = None,
    reference: str = "",
    note: str = "",
    actor=None,
) -> UpstreamSettlement:
    """Record money moving to or from the upstream operator."""
    amount = Decimal(amount)
    if amount <= 0:
        raise BillingError("A settlement must be greater than zero.")
    if kind not in UpstreamSettlement.Kind.values:
        raise BillingError(f"Unknown settlement type: {kind}.")

    settlement = UpstreamSettlement.objects.create(
        kind=kind,
        amount=amount,
        period=month_start(period),
        settled_on=settled_on or timezone.localdate(),
        reference=reference,
        note=note,
        created_by=actor,
    )
    logger.info("settlement recorded kind=%s amount=%s period=%s", kind, amount, settlement.period)
    return settlement


@transaction.atomic
def change_package(
    client: Client,
    package,
    *,
    monthly_price=None,
    discount=None,
    commission_percent=None,
    actor=None,
) -> Subscription:
    """Move a client to a different plan, keeping the old subscription as history.

    `commission_percent` is an optional per-client override; left as None the
    subscription falls back to the package's rate and then to billing settings.
    """
    current = client.subscription
    unchanged = (
        current
        and current.package_id == package.pk
        and monthly_price is None
        and commission_percent is None
    )
    if unchanged:
        return current
    if current:
        current.cancel()
    return Subscription.objects.create(
        client=client,
        package=package,
        monthly_price=package.monthly_price if monthly_price is None else monthly_price,
        discount=discount if discount is not None else Decimal("0.00"),
        commission_percent=commission_percent,
        created_by=actor,
    )
