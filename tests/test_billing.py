"""Billing rules. These are the tests that protect the books."""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.accountants.models import Invoice, Payment
from apps.accountants.services import (
    BillingError,
    cancel_invoice,
    change_package,
    generate_invoices,
    record_payment,
    refresh_overdue,
)
from apps.accounts.models import Client, Package, Subscription
from apps.core.utils import add_months


def test_generates_one_invoice_per_billable_client(make_client_record, period):
    make_client_record(username="c1")
    make_client_record(username="c2")
    result = generate_invoices(period)
    assert result.created_count == 2
    assert Invoice.objects.count() == 2


def test_generation_is_idempotent(client_record, period):
    generate_invoices(period)
    second = generate_invoices(period)
    assert second.created_count == 0
    assert second.skipped == [(client_record.client_code, "already invoiced")]
    assert Invoice.objects.count() == 1


def test_terminated_clients_are_not_billed(make_client_record, period):
    make_client_record(username="gone", status=Client.Status.TERMINATED)
    assert generate_invoices(period).created_count == 0


def test_suspended_clients_are_still_billed(make_client_record, period):
    """A suspension is a service state, not a debt forgiveness."""
    make_client_record(username="susp", status=Client.Status.SUSPENDED)
    assert generate_invoices(period).created_count == 1


def test_client_without_a_subscription_is_skipped(pop, period):
    client = Client.objects.create(
        name="No plan",
        username="noplan",
        phone="01712345678",
        address="x",
        pop=pop,
        status=Client.Status.ACTIVE,
    )
    result = generate_invoices(period)
    assert result.created_count == 0
    assert result.skipped == [(client.client_code, "no active subscription")]


def test_invoice_total_applies_the_subscription_discount(make_client_record, period):
    make_client_record(username="disc", price="800.00", discount="50.00")
    generate_invoices(period)
    invoice = Invoice.objects.get()
    assert invoice.subtotal == Decimal("800.00")
    assert invoice.discount == Decimal("50.00")
    assert invoice.total == Decimal("750.00")


def test_dry_run_writes_nothing(client_record, period):
    result = generate_invoices(period, dry_run=True)
    assert result.created_count == 1
    assert Invoice.objects.count() == 0


def test_invoice_numbers_are_sequential_within_a_period(make_client_record, period):
    make_client_record(username="n1")
    make_client_record(username="n2")
    generate_invoices(period)
    numbers = sorted(Invoice.objects.values_list("number", flat=True))
    stamp = period.strftime("%Y%m")
    assert numbers == [f"INV-{stamp}-0001", f"INV-{stamp}-0002"]


def test_payment_moves_the_invoice_to_paid(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    record_payment(invoice, invoice.total)
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.PAID
    assert invoice.amount_due == Decimal("0.00")


def test_partial_payment_is_reported_as_partial(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    record_payment(invoice, Decimal("300.00"))
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.PARTIAL
    assert invoice.amount_due == Decimal("500.00")


def test_overpayment_is_refused(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    with pytest.raises(BillingError, match="more than"):
        record_payment(invoice, invoice.total + Decimal("1.00"))
    assert Payment.objects.count() == 0


def test_zero_payment_is_refused(client_record, period):
    generate_invoices(period)
    with pytest.raises(BillingError):
        record_payment(Invoice.objects.get(), Decimal("0.00"))


def test_reversing_a_payment_restores_the_balance(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    payment = record_payment(invoice, invoice.total)
    payment.delete()
    invoice.refresh_from_db()
    assert invoice.amount_paid == Decimal("0.00")
    assert invoice.status != Invoice.Status.PAID


def test_payment_denormalises_its_client(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    payment = record_payment(invoice, Decimal("100.00"))
    assert payment.client_id == client_record.pk


def test_cancelled_invoice_refuses_payment(client_record, period):
    generate_invoices(period)
    invoice = cancel_invoice(Invoice.objects.get())
    with pytest.raises(BillingError, match="cancelled"):
        record_payment(invoice, Decimal("10.00"))


def test_paid_invoice_cannot_be_cancelled(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    record_payment(invoice, invoice.total)
    with pytest.raises(BillingError, match="Refund"):
        cancel_invoice(invoice)


def test_cancelling_frees_the_period_for_a_new_invoice(client_record, period):
    """The partial unique index excludes cancelled rows, so a re-bill is possible."""
    generate_invoices(period)
    cancel_invoice(Invoice.objects.get())
    assert generate_invoices(period).created_count == 1
    assert Invoice.objects.exclude(status=Invoice.Status.CANCELLED).count() == 1


def test_refresh_overdue_flags_late_invoices(client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    Invoice.objects.filter(pk=invoice.pk).update(
        due_date=invoice.issue_date - timedelta(days=5), status=Invoice.Status.UNPAID
    )
    assert refresh_overdue() == 1
    assert Invoice.objects.get().status == Invoice.Status.OVERDUE


def test_changing_package_keeps_the_old_price_on_past_invoices(client_record, period, package):
    generate_invoices(period)
    original = Invoice.objects.get().total

    premium = Package.objects.create(
        name="Pro 50", bandwidth_mbps=50, monthly_price=Decimal("1800.00")
    )
    change_package(client_record, premium)

    client_record.refresh_from_db()
    assert client_record.subscription.package == premium
    assert Invoice.objects.get().total == original
    assert client_record.subscriptions.filter(status=Subscription.Status.CANCELLED).count() == 1


def test_repricing_a_package_does_not_change_existing_subscriptions(client_record, package):
    package.monthly_price = Decimal("9999.00")
    package.save()
    client_record.refresh_from_db()
    assert client_record.subscription.monthly_price == Decimal("800.00")


def test_a_client_joining_later_is_not_billed_for_earlier_months(make_client_record, period):
    record = make_client_record(username="new")
    subscription = record.subscription
    subscription.start_date = add_months(period, 1)
    subscription.save()
    result = generate_invoices(period)
    assert result.created_count == 0
    assert result.skipped == [(record.client_code, "subscription not active in period")]


def test_period_is_normalised_to_the_first_of_the_month(client_record):
    """Any date inside the month bills that whole month."""
    from datetime import date

    subscription = client_record.subscription
    subscription.start_date = date(2026, 1, 1)
    subscription.save()

    generate_invoices(date(2026, 3, 17))
    assert Invoice.objects.get().period == date(2026, 3, 1)


def test_issue_date_follows_the_client_billing_day(make_client_record, period):
    make_client_record(username="bd", billing_day=15)
    generate_invoices(period)
    invoice = Invoice.objects.get()
    assert invoice.issue_date.day == 15
    assert invoice.due_date == invoice.issue_date + timedelta(days=10)
