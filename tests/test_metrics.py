"""Dashboard arithmetic. A wrong number here is worse than a crash."""

from decimal import Decimal

from apps.accountants.models import Expense, Income
from apps.accountants.services import generate_invoices, record_payment
from apps.accounts.models import Client
from apps.reports import metrics


def test_mrr_counts_only_active_clients(make_client_record):
    make_client_record(username="m1", price="800.00")
    make_client_record(username="m2", price="500.00")
    make_client_record(username="m3", price="900.00", status=Client.Status.TERMINATED)
    assert metrics.mrr() == Decimal("1300.00")


def test_mrr_is_net_of_discounts(make_client_record):
    make_client_record(username="d1", price="800.00", discount="100.00")
    assert metrics.mrr() == Decimal("700.00")


def test_arpu_divides_by_active_clients(make_client_record):
    make_client_record(username="a1", price="800.00")
    make_client_record(username="a2", price="400.00")
    assert metrics.arpu() == Decimal("600.00")


def test_arpu_is_zero_rather_than_an_error_when_empty(db):
    assert metrics.arpu() == Decimal("0.00")


def test_payments_count_cash_not_invoices(client_record, period):
    generate_invoices(period)
    assert metrics.billed(period) == Decimal("800.00")
    assert metrics.client_payments(period) == Decimal("0.00")


def test_collection_rate_reflects_partial_payment(client_record, period):
    from apps.accountants.models import Invoice

    generate_invoices(period)
    invoice = Invoice.objects.get()
    record_payment(invoice, Decimal("200.00"), received_on=invoice.issue_date)
    assert metrics.collection_rate(period) == 25.0


def test_collection_rate_is_zero_when_nothing_billed(db, period):
    assert metrics.collection_rate(period) == 0.0


def test_outstanding_sums_every_unpaid_invoice(make_client_record, period):
    make_client_record(username="o1")
    make_client_record(username="o2")
    generate_invoices(period)
    assert metrics.outstanding_total() == Decimal("1600.00")


def test_profit_counts_commission_not_gross_collections(client_record, period):
    """The upstream share is not the reseller's money, even when they hold it."""
    from apps.accountants.models import Invoice

    generate_invoices(period)
    invoice = Invoice.objects.get()
    record_payment(invoice, Decimal("800.00"), received_on=period)
    Income.objects.create(description="Install", amount=Decimal("200.00"), occurred_on=period)
    Expense.objects.create(description="Fuel", amount=Decimal("100.00"), occurred_on=period)

    result = metrics.profit(period)
    # 800 collected at 20% = 160 commission, plus 200 other income.
    assert result["commission"] == Decimal("160.00")
    assert result["revenue"] == Decimal("360.00")
    assert result["expenses"] == Decimal("100.00")
    assert result["net"] == Decimal("260.00")


def test_commission_split_accounts_for_every_paisa(client_record, period):
    from apps.accountants.models import Invoice

    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    split = metrics.commission_split(period)

    assert split["client_payments"] == Decimal("800.00")
    assert split["commission_earned"] == Decimal("160.00")
    assert split["owed_upstream"] == Decimal("640.00")
    # Nothing is lost between the two halves.
    assert split["commission_earned"] + split["owed_upstream"] == split["client_payments"]


def test_revenue_trend_returns_one_row_per_month(db, period):
    trend = metrics.revenue_trend(12, period)
    assert len(trend) == 12
    assert trend[-1]["period"] == period
    assert trend[0]["period"] < trend[-1]["period"]


def test_the_chart_axis_rounds_up_to_a_readable_ceiling():
    """A raw peak of 13,935.75 gives ticks nobody can read; the axis lifts it."""
    from decimal import Decimal

    from apps.core.templatetags.charts import nice_ceiling

    assert nice_ceiling(13935.75) == Decimal("15000")
    assert nice_ceiling(47500) == Decimal("50000")
    # Never zero: the bar heights divide by it.
    assert nice_ceiling(0) > 0


def test_aging_buckets_cover_every_outstanding_invoice(client_record, period):
    generate_invoices(period)
    total = sum(bucket["amount"] for bucket in metrics.aging_buckets())
    assert total == metrics.outstanding_total()


def test_dashboard_assembles_without_any_data(db, period):
    payload = metrics.dashboard(period)
    assert payload["clients"]["total"] == 0
    assert payload["mrr"] == Decimal("0.00")
    assert payload["profit"]["net"] == Decimal("0.00")


def test_client_snapshot_counts_by_status(make_client_record):
    make_client_record(username="s1")
    make_client_record(username="s2", status=Client.Status.SUSPENDED)
    snapshot = metrics.client_snapshot()
    assert snapshot["total"] == 2
    assert snapshot["active"] == 1
    assert snapshot["active_percent"] == 50.0


def test_a_figures_scope_computes_each_leaf_once(db, period):
    """Guards the dashboard's query count.

    Without the scope the same figure is fetched several times per page —
    `revenue` also sits inside `profit`, `client_payments` inside both
    `collection_rate` and `commission_split`.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as unscoped:
        for _ in range(5):
            metrics.revenue(period)
    assert len(unscoped) == 10  # two aggregates per call, five times

    with CaptureQueriesContext(connection) as scoped, metrics.figures_scope():
        for _ in range(5):
            metrics.revenue(period)
    assert len(scoped) == 2  # computed once


def test_the_scope_does_not_outlive_its_block(db, period):
    """A figure read after a write must be the new number, not a cached one."""
    from decimal import Decimal

    with metrics.figures_scope():
        before = metrics.other_income(period)

    Income.objects.create(description="probe", amount=Decimal("500.00"), occurred_on=period)

    with metrics.figures_scope():
        assert metrics.other_income(period) == before + Decimal("500.00")


def test_dashboard_query_count_stays_bounded(db, period, django_assert_max_num_queries):
    """A dashboard is a lot of aggregates; it must not become a lot more."""
    with django_assert_max_num_queries(60):
        metrics.dashboard(period)
