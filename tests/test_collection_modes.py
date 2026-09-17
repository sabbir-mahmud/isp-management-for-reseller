"""The two settlement arrangements, and the money that moves under each.

Arrangement A (`RESELLER`): the reseller collects the bill, keeps the
commission and owes the rest upstream.
Arrangement B (`UPSTREAM`): the customer pays the upstream operator directly
and the upstream operator owes the reseller their commission.
"""

from decimal import Decimal

import pytest

from apps.accountants.models import BillingSettings, Invoice, Payment, UpstreamSettlement
from apps.accountants.services import (
    BillingError,
    generate_invoices,
    record_payment,
    record_settlement,
    upstream_position,
)
from apps.accounts.models import Package
from apps.core.choices import CollectionMode
from apps.core.utils import split_commission
from apps.reports import metrics


@pytest.fixture
def settings_row(db):
    return BillingSettings.load()


# ---------------------------------------------------------------------------#
# The split itself
# ---------------------------------------------------------------------------#


@pytest.mark.parametrize(
    "amount,percent",
    [
        ("800.00", "20.00"),
        ("333.33", "15.00"),
        ("0.01", "33.33"),
        ("1234.56", "7.50"),
        ("999.99", "99.99"),
    ],
)
def test_the_split_always_adds_back_to_the_original(amount, percent):
    """Rounding each half separately would leak a paisa on roughly half of all bills."""
    commission, upstream = split_commission(Decimal(amount), Decimal(percent))
    assert commission + upstream == Decimal(amount)
    assert commission >= 0 and upstream >= 0


def test_a_zero_commission_leaves_everything_upstream():
    commission, upstream = split_commission(Decimal("500.00"), Decimal("0"))
    assert commission == Decimal("0.00")
    assert upstream == Decimal("500.00")


def test_a_full_commission_leaves_nothing_upstream():
    commission, upstream = split_commission(Decimal("500.00"), Decimal("100"))
    assert commission == Decimal("500.00")
    assert upstream == Decimal("0.00")


# ---------------------------------------------------------------------------#
# Resolving which arrangement and rate apply
# ---------------------------------------------------------------------------#


def test_a_client_follows_the_business_default(settings_row, client_record):
    settings_row.collection_mode = CollectionMode.UPSTREAM
    settings_row.save()
    assert client_record.collection_mode == ""
    assert client_record.effective_collection_mode == CollectionMode.UPSTREAM
    assert client_record.pays_upstream_directly is True


def test_a_client_can_override_the_default(settings_row, make_client_record):
    """A reseller's base is usually mixed, so the per-client value has to win."""
    settings_row.collection_mode = CollectionMode.RESELLER
    settings_row.save()

    record = make_client_record(username="online", collection_mode=CollectionMode.UPSTREAM)
    assert record.effective_collection_mode == CollectionMode.UPSTREAM


def test_commission_falls_back_from_subscription_to_package_to_settings(
    settings_row, client_record, package
):
    subscription = client_record.subscription
    assert subscription.effective_commission_percent == settings_row.commission_percent

    package.commission_percent = Decimal("30.00")
    package.save()
    subscription.refresh_from_db()
    assert subscription.effective_commission_percent == Decimal("30.00")

    subscription.commission_percent = Decimal("35.00")
    subscription.save()
    assert subscription.effective_commission_percent == Decimal("35.00")


# ---------------------------------------------------------------------------#
# Generation stamps the arrangement onto the invoice
# ---------------------------------------------------------------------------#


def test_generation_stamps_the_default_arrangement(settings_row, client_record, period):
    settings_row.collection_mode = CollectionMode.UPSTREAM
    settings_row.save()

    generate_invoices(period)
    invoice = Invoice.objects.get()
    assert invoice.collection_mode == CollectionMode.UPSTREAM
    assert invoice.collected_by_reseller is False


def test_generation_honours_a_per_client_override(settings_row, make_client_record, period):
    settings_row.collection_mode = CollectionMode.RESELLER
    settings_row.save()
    make_client_record(username="mine")
    make_client_record(username="theirs", collection_mode=CollectionMode.UPSTREAM)

    result = generate_invoices(period)
    assert len(result.reseller_collected) == 1
    assert len(result.upstream_collected) == 1
    assert result.to_collect_total == Decimal("800.00")


def test_the_invoice_records_its_own_commission_split(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    assert invoice.commission_percent == Decimal("20.00")
    assert invoice.commission_amount == Decimal("160.00")
    assert invoice.upstream_amount == Decimal("640.00")
    assert invoice.commission_amount + invoice.upstream_amount == invoice.total


def test_changing_the_rate_later_does_not_restate_past_invoices(
    settings_row, client_record, period
):
    generate_invoices(period)
    settings_row.commission_percent = Decimal("50.00")
    settings_row.save()

    invoice = Invoice.objects.get()
    invoice.recalculate()
    assert invoice.commission_percent == Decimal("20.00")
    assert invoice.commission_amount == Decimal("160.00")


def test_switching_the_business_mode_does_not_restate_past_invoices(
    settings_row, client_record, period
):
    generate_invoices(period)
    settings_row.collection_mode = CollectionMode.UPSTREAM
    settings_row.save()
    assert Invoice.objects.get().collection_mode == CollectionMode.RESELLER


def test_a_package_rate_flows_into_new_invoices(settings_row, pop, make_client_record, period):
    premium = Package.objects.create(
        name="Pro 50",
        bandwidth_mbps=50,
        monthly_price=Decimal("1000.00"),
        commission_percent=Decimal("25.00"),
    )
    record = make_client_record(username="pro")
    # Held in a local: `client.subscription` re-queries on each access when the
    # queryset was not prefetched, so chained attribute writes would land on
    # three different instances and none of them would be saved.
    subscription = record.subscription
    subscription.package = premium
    subscription.monthly_price = premium.monthly_price
    subscription.save()

    generate_invoices(period)
    invoice = Invoice.objects.get()
    assert invoice.commission_percent == Decimal("25.00")
    assert invoice.commission_amount == Decimal("250.00")


# ---------------------------------------------------------------------------#
# Payments carry the arrangement
# ---------------------------------------------------------------------------#


def test_a_payment_earns_commission_in_proportion(client_record, period):
    """Half the bill paid must earn half the commission, not all of it."""
    generate_invoices(period)
    invoice = Invoice.objects.get()
    payment = record_payment(invoice, Decimal("400.00"), received_on=period)
    assert payment.commission_amount == Decimal("80.00")
    assert payment.upstream_amount == Decimal("320.00")


def test_reseller_collected_payments_are_cash_in_hand(client_record, period):
    generate_invoices(period)
    payment = record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    assert payment.is_reseller_cash is True
    assert metrics.reseller_cash(period) == Decimal("800.00")
    assert metrics.upstream_direct(period) == Decimal("0.00")


def test_upstream_collected_payments_never_count_as_reseller_cash(
    settings_row, make_client_record, period
):
    make_client_record(username="direct", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)
    payment = record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)

    assert payment.is_reseller_cash is False
    assert metrics.reseller_cash(period) == Decimal("0.00")
    assert metrics.upstream_direct(period) == Decimal("800.00")
    # The reseller still earns the commission on it.
    assert metrics.commission_earned(period) == Decimal("160.00")


def test_revenue_is_the_same_under_both_arrangements(settings_row, make_client_record, period):
    """The arrangement changes who holds the cash, never what the reseller earns."""
    make_client_record(username="mine")
    make_client_record(username="theirs", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)
    for invoice in Invoice.objects.all():
        record_payment(invoice, invoice.total, received_on=period)

    assert metrics.client_payments(period) == Decimal("1600.00")
    assert metrics.commission_earned(period) == Decimal("320.00")
    assert metrics.revenue(period) == Decimal("320.00")


# ---------------------------------------------------------------------------#
# Settling up with the upstream operator
# ---------------------------------------------------------------------------#


def test_collecting_creates_a_liability_to_upstream(client_record, period):
    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)

    position = upstream_position()
    assert position["owed_upstream"] == Decimal("640.00")
    assert position["payable"] == Decimal("640.00")
    assert position["receivable"] == Decimal("0.00")


def test_remitting_clears_the_liability(client_record, period):
    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    record_settlement(UpstreamSettlement.Kind.REMITTANCE, Decimal("640.00"), period=period)

    assert upstream_position()["payable"] == Decimal("0.00")


def test_a_partial_remittance_leaves_the_balance(client_record, period):
    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    record_settlement(UpstreamSettlement.Kind.REMITTANCE, Decimal("400.00"), period=period)

    assert upstream_position()["payable"] == Decimal("240.00")


def test_upstream_collection_creates_a_receivable(settings_row, make_client_record, period):
    make_client_record(username="direct", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)

    position = upstream_position()
    assert position["receivable"] == Decimal("160.00")
    # Nothing is owed the other way: the reseller never held this money.
    assert position["payable"] == Decimal("0.00")


def test_a_commission_payout_clears_the_receivable(settings_row, make_client_record, period):
    make_client_record(username="direct", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    record_settlement(UpstreamSettlement.Kind.COMMISSION_PAYOUT, Decimal("160.00"), period=period)

    assert upstream_position()["receivable"] == Decimal("0.00")


def test_both_balances_run_independently(settings_row, make_client_record, period):
    """A mixed base owes upstream and is owed by upstream at the same time."""
    make_client_record(username="mine")
    make_client_record(username="theirs", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)
    for invoice in Invoice.objects.all():
        record_payment(invoice, invoice.total, received_on=period)

    position = upstream_position()
    assert position["payable"] == Decimal("640.00")
    assert position["receivable"] == Decimal("160.00")


def test_a_settlement_is_scoped_to_its_month(client_record, period):
    from apps.core.utils import add_months

    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    record_settlement(UpstreamSettlement.Kind.REMITTANCE, Decimal("640.00"), period=period)

    assert upstream_position(period)["payable"] == Decimal("0.00")
    # A different month has neither the collection nor the remittance.
    assert upstream_position(add_months(period, -1))["payable"] == Decimal("0.00")


def test_a_zero_settlement_is_refused(db):
    with pytest.raises(BillingError, match="greater than zero"):
        record_settlement(UpstreamSettlement.Kind.REMITTANCE, Decimal("0.00"))


def test_an_unknown_settlement_type_is_refused(db):
    with pytest.raises(BillingError, match="Unknown settlement type"):
        record_settlement("bribe", Decimal("100.00"))


def test_settlement_period_is_normalised_to_the_month(db):
    from datetime import date

    settlement = record_settlement(
        UpstreamSettlement.Kind.REMITTANCE, Decimal("100.00"), period=date(2026, 5, 23)
    )
    assert settlement.period == date(2026, 5, 1)


def test_arrears_are_split_by_who_must_chase_them(settings_row, make_client_record, period):
    make_client_record(username="mine")
    make_client_record(username="theirs", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)

    split = metrics.outstanding_by_mode()
    assert split["reseller"] == Decimal("800.00")
    assert split["upstream"] == Decimal("800.00")


def test_mode_mix_resolves_the_inherited_default(settings_row, make_client_record):
    settings_row.collection_mode = CollectionMode.RESELLER
    settings_row.save()
    make_client_record(username="a")
    make_client_record(username="b")
    make_client_record(username="c", collection_mode=CollectionMode.UPSTREAM)

    mix = metrics.mode_mix()
    assert mix == {"reseller": 2, "upstream": 1, "total": 3}


def test_reversing_a_payment_reverses_its_commission(client_record, period):
    generate_invoices(period)
    payment = record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    payment.delete()

    assert Payment.objects.count() == 0
    assert metrics.commission_earned(period) == Decimal("0.00")
    assert upstream_position()["payable"] == Decimal("0.00")
