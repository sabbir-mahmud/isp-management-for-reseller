"""Business metrics.

One module owns every number the dashboard shows, so a figure cannot mean one
thing on the dashboard and another on the P&L page. Each function returns
plain data and takes the period as an argument — that is what makes them
testable and what lets the same code answer "this month" and "last March".
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.accountants.models import BillingSettings, Expense, Income, Invoice, Payment
from apps.accountants.services import upstream_position
from apps.accounts.models import Client, Subscription
from apps.core.choices import CollectionMode
from apps.core.utils import add_months, month_end, month_range, month_start, percentage
from apps.warehouse.models import Onu, Product

ZERO = Value(Decimal("0.00"), output_field=DecimalField(max_digits=14, decimal_places=2))


def _sum(queryset, field) -> Decimal:
    return queryset.aggregate(total=Coalesce(Sum(field), ZERO))["total"]


@dataclass
class Money:
    """A figure plus its month-over-month movement, for the KPI cards."""

    value: Decimal
    previous: Decimal = Decimal("0.00")

    @property
    def delta(self) -> Decimal:
        return self.value - self.previous

    @property
    def delta_percent(self) -> float:
        return percentage(self.delta, self.previous) if self.previous else 0.0

    @property
    def direction(self) -> str:
        if self.delta > 0:
            return "up"
        return "down" if self.delta < 0 else "flat"


def client_snapshot() -> dict:
    counts = Client.objects.aggregate(
        total=Count("pk"),
        active=Count("pk", filter=Q(status=Client.Status.ACTIVE)),
        suspended=Count("pk", filter=Q(status=Client.Status.SUSPENDED)),
        pending=Count("pk", filter=Q(status=Client.Status.PENDING)),
        terminated=Count("pk", filter=Q(status=Client.Status.TERMINATED)),
    )
    counts["active_percent"] = percentage(counts["active"], counts["total"])
    return counts


def inventory_snapshot() -> dict:
    onu = Onu.objects.aggregate(
        total=Count("pk"),
        in_stock=Count("pk", filter=Q(status=Onu.Status.IN_STOCK)),
        assigned=Count("pk", filter=Q(status=Onu.Status.ASSIGNED)),
        faulty=Count("pk", filter=Q(status=Onu.Status.FAULTY)),
    )
    stock = Product.objects.aggregate(
        skus=Count("pk"),
        units=Coalesce(Sum("quantity"), Value(0)),
        value=Coalesce(Sum(F("quantity") * F("unit_price"), output_field=DecimalField()), ZERO),
    )
    onu["stock_skus"] = stock["skus"]
    onu["stock_units"] = stock["units"]
    onu["stock_value"] = stock["value"]
    onu["low_stock"] = Product.objects.low_stock().count()
    return onu


def mrr() -> Decimal:
    """Monthly recurring revenue: what live subscriptions are worth per month.

    A forecast, and labelled as one. Cash actually collected is `collected()`.
    """
    return _sum(
        Subscription.objects.active().filter(client__status=Client.Status.ACTIVE),
        F("monthly_price") - F("discount"),
    )


def arpu() -> Decimal:
    active = Client.objects.active().count()
    return (mrr() / active).quantize(Decimal("0.01")) if active else Decimal("0.00")


def billed(period: date) -> Decimal:
    """Everything invoiced for the period, under either arrangement."""
    return _sum(
        Invoice.objects.for_period(period).exclude(status=Invoice.Status.CANCELLED), "total"
    )


def _payments_in(period: date):
    """Payments received during the calendar month, whatever period they settle."""
    return Payment.objects.filter(received_on__range=(month_start(period), month_end(period)))


def client_payments(period: date) -> Decimal:
    """Gross customer payments, across both arrangements.

    This is what customers paid, not what the reseller earned. Under the
    `UPSTREAM` arrangement none of it ever reaches the reseller's hands.
    """
    return _sum(_payments_in(period), "amount")


def reseller_cash(period: date) -> Decimal:
    """Money the reseller physically collected and is holding.

    Part of it belongs upstream until it is remitted — see
    `services.upstream_position`.
    """
    return _sum(_payments_in(period).filter(collection_mode=CollectionMode.RESELLER), "amount")


def upstream_direct(period: date) -> Decimal:
    """Bills customers paid to the upstream operator directly."""
    return _sum(_payments_in(period).filter(collection_mode=CollectionMode.UPSTREAM), "amount")


def commission_earned(period: date) -> Decimal:
    """The reseller's actual earnings on customer payments.

    Commission is accrued per payment rather than per invoice, so a half-paid
    bill earns half its commission instead of all of it up front.
    """
    return _sum(_payments_in(period), "commission_amount")


def other_income(period: date) -> Decimal:
    start, end = month_start(period), month_end(period)
    return _sum(Income.objects.filter(occurred_on__range=(start, end)), "amount")


def revenue(period: date) -> Decimal:
    """What the business actually earned: commission plus non-subscription income.

    Deliberately *not* gross collections. Under the `RESELLER` arrangement the
    upstream share is somebody else's money passing through; counting it as
    revenue overstates the business by whatever the upstream share happens to
    be — typically four fifths of it.
    """
    return commission_earned(period) + other_income(period)


def expenses(period: date) -> Decimal:
    start, end = month_start(period), month_end(period)
    return _sum(Expense.objects.filter(occurred_on__range=(start, end)), "amount")


def outstanding_total() -> Decimal:
    """Everything customers still owe, across all periods and both arrangements."""
    return _sum(Invoice.objects.outstanding(), F("total") - F("amount_paid"))


def outstanding_by_mode() -> dict:
    """Split the arrears by who is responsible for chasing them.

    The reseller collects one pile themselves; the other is the upstream
    operator's to collect, and only costs the reseller the commission.
    """
    rows = Invoice.objects.outstanding()
    return {
        "reseller": _sum(
            rows.filter(collection_mode=CollectionMode.RESELLER), F("total") - F("amount_paid")
        ),
        "upstream": _sum(
            rows.filter(collection_mode=CollectionMode.UPSTREAM), F("total") - F("amount_paid")
        ),
    }


def collection_rate(period: date) -> float:
    """Share of the month's billing that customers have paid, either way."""
    return percentage(client_payments(period), billed(period))


def churn_rate(period: date) -> float:
    """Share of the month's starting subscriber base that terminated in it."""
    start, end = month_start(period), month_end(period)
    lost = Subscription.objects.filter(
        status=Subscription.Status.CANCELLED, end_date__range=(start, end)
    ).count()
    base = (
        Subscription.objects.filter(start_date__lt=start)
        .exclude(status=Subscription.Status.CANCELLED, end_date__lt=start)
        .count()
    )
    return percentage(lost, base)


def commission_split(period: date) -> dict:
    """How the month's customer payments divide, and who is holding what."""
    settings_row = BillingSettings.load()
    position = upstream_position(period)

    return {
        "default_mode": settings_row.collection_mode,
        "default_mode_display": settings_row.get_collection_mode_display(),
        "upstream_name": settings_row.upstream_name or "upstream",
        "commission_percent": settings_row.commission_percent,
        "client_payments": client_payments(period),
        "reseller_cash": reseller_cash(period),
        "upstream_direct": upstream_direct(period),
        "commission_earned": commission_earned(period),
        # Owed to the upstream operator out of cash the reseller collected.
        "owed_upstream": position["owed_upstream"],
        "remitted": position["remitted"],
        "payable": position["payable"],
        # Owed by the upstream operator for bills customers paid them directly.
        "commission_receivable": position["receivable"],
    }


def mode_mix() -> dict:
    """How many clients sit under each arrangement.

    Resolved per client, so it accounts for the ones overriding the default.
    """
    settings_row = BillingSettings.load()
    default = settings_row.collection_mode
    counts = Client.objects.active().aggregate(
        explicit_reseller=Count("pk", filter=Q(collection_mode=CollectionMode.RESELLER)),
        explicit_upstream=Count("pk", filter=Q(collection_mode=CollectionMode.UPSTREAM)),
        inherited=Count("pk", filter=Q(collection_mode="")),
    )
    reseller = counts["explicit_reseller"]
    upstream = counts["explicit_upstream"]
    if default == CollectionMode.RESELLER:
        reseller += counts["inherited"]
    else:
        upstream += counts["inherited"]
    return {"reseller": reseller, "upstream": upstream, "total": reseller + upstream}


def profit(period: date) -> dict:
    """Net for the month: commission and other income, minus expenses."""
    earned = revenue(period)
    spend = expenses(period)
    return {
        "revenue": earned,
        "commission": commission_earned(period),
        "other_income": other_income(period),
        "expenses": spend,
        "net": earned - spend,
        "margin": percentage(earned - spend, earned),
    }


def revenue_trend(months: int = 12, end: date | None = None) -> list[dict]:
    """Earned revenue vs expenses per month, in grouped queries rather than 2N.

    Revenue here is commission plus other income — the same definition the
    KPI cards use — so the chart and the profit figure cannot disagree.
    """
    periods = month_range(end, months)
    start = periods[0]
    finish = month_end(periods[-1])

    def _bucketed(queryset, date_field, amount_field):
        """Sum `amount_field` per month, keyed by a plain `date` month-start.

        `TruncMonth` yields a `date` on SQLite and a `datetime` on Postgres,
        so the keys are normalised here rather than at every lookup.
        """
        rows = (
            queryset.filter(**{f"{date_field}__range": (start, finish)})
            .annotate(bucket=TruncMonth(date_field))
            .values("bucket")
            .annotate(total=Coalesce(Sum(amount_field), ZERO))
            .values_list("bucket", "total")
        )
        return {
            (bucket.date() if hasattr(bucket, "date") else bucket): total for bucket, total in rows
        }

    commissions = _bucketed(Payment.objects.all(), "received_on", "commission_amount")
    gross = _bucketed(Payment.objects.all(), "received_on", "amount")
    incomes = _bucketed(Income.objects.all(), "occurred_on", "amount")
    spends = _bucketed(Expense.objects.all(), "occurred_on", "amount")

    trend = []
    for period in periods:
        earned = commissions.get(period, Decimal("0.00")) + incomes.get(period, Decimal("0.00"))
        spend = spends.get(period, Decimal("0.00"))
        trend.append(
            {
                "period": period,
                "label": period.strftime("%b %y"),
                "revenue": earned,
                "gross": gross.get(period, Decimal("0.00")),
                "expenses": spend,
                "net": earned - spend,
            }
        )
    return trend


def aging_buckets(today: date | None = None) -> list[dict]:
    """Outstanding money by how long it has been outstanding."""
    today = today or timezone.localdate()
    definitions = [
        ("Not yet due", None, 0),
        ("1–30 days", 0, 30),
        ("31–60 days", 30, 60),
        ("60+ days", 60, None),
    ]
    rows = []
    for label, lower, upper in definitions:
        queryset = Invoice.objects.outstanding()
        if lower is None:
            queryset = queryset.filter(due_date__gte=today)
        else:
            queryset = queryset.filter(due_date__lt=today - _days(lower))
            if upper is not None:
                queryset = queryset.filter(due_date__gte=today - _days(upper))
        # One aggregate per bucket rather than a count query and a sum query.
        totals = queryset.aggregate(
            count=Count("pk"), amount=Coalesce(Sum(F("total") - F("amount_paid")), ZERO)
        )
        rows.append({"label": label, "count": totals["count"], "amount": totals["amount"]})
    return rows


def _days(count: int):
    from datetime import timedelta

    return timedelta(days=count)


def top_debtors(limit: int = 10):
    return (
        Client.objects.filter(invoices__in=Invoice.objects.outstanding())
        .annotate(due=Coalesce(Sum(F("invoices__total") - F("invoices__amount_paid")), ZERO))
        .filter(due__gt=0)
        .order_by("-due")[:limit]
    )


def package_mix():
    return (
        Subscription.objects.active()
        .values("package__name")
        .annotate(
            subscribers=Count("pk"),
            revenue=Coalesce(Sum(F("monthly_price") - F("discount")), ZERO),
        )
        .order_by("-subscribers")
    )


def pop_mix():
    return (
        Client.objects.values("pop__name")
        .annotate(
            total=Count("pk"),
            active=Count("pk", filter=Q(status=Client.Status.ACTIVE)),
        )
        .order_by("-total")
    )


def trend_ceiling(trend: list[dict]) -> Decimal:
    """The tallest bar in a trend, used to scale the chart.

    Never zero: the template divides by it, and an all-zero month would
    otherwise render as a division error rather than an empty chart.
    """
    values = [row["revenue"] for row in trend] + [row["expenses"] for row in trend]
    return max(values + [Decimal("1.00")])


def dashboard(period: date | None = None) -> dict:
    """Everything the dashboard renders, assembled once."""
    period = month_start(period)
    prior = add_months(period, -1)
    trend = revenue_trend(12, period)

    return {
        "period": period,
        "previous_period": prior,
        "clients": client_snapshot(),
        "inventory": inventory_snapshot(),
        "mrr": mrr(),
        "arpu": arpu(),
        "billed": Money(billed(period), billed(prior)),
        "client_payments": Money(client_payments(period), client_payments(prior)),
        "revenue": Money(revenue(period), revenue(prior)),
        "commission_earned": Money(commission_earned(period), commission_earned(prior)),
        "reseller_cash": Money(reseller_cash(period), reseller_cash(prior)),
        "upstream_direct": Money(upstream_direct(period), upstream_direct(prior)),
        "expenses": Money(expenses(period), expenses(prior)),
        "outstanding": outstanding_total(),
        "outstanding_by_mode": outstanding_by_mode(),
        "collection_rate": collection_rate(period),
        "churn_rate": churn_rate(period),
        "commission": commission_split(period),
        "mode_mix": mode_mix(),
        "upstream": upstream_position(),
        "profit": profit(period),
        "trend": trend,
        "max_trend": trend_ceiling(trend),
        "aging": aging_buckets(),
        "debtors": top_debtors(),
        "package_mix": package_mix(),
        "pop_mix": pop_mix(),
    }
