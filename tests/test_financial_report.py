"""The financial report: the statement, its comparison column, and the page.

The statement is the one place the business's result is stated, so the tests
here are mostly identities — if revenue stops equalling its parts, the page is
lying regardless of how it looks.
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accountants.models import Expense, Income, Invoice
from apps.accountants.services import generate_invoices, record_payment
from apps.core.utils import add_months, month_start
from apps.reports import metrics
from apps.users.models import Role
from apps.users.roles import sync_roles


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("reportboss", Role.OWNER))
    return client


@pytest.fixture
def a_month_of_trading(client_record, period):
    """One paid invoice, one expense, one bit of other income."""
    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)
    Income.objects.create(description="Install", amount=Decimal("200.00"), occurred_on=period)
    Expense.objects.create(
        description="Salary",
        category=Expense.Category.SALARY,
        amount=Decimal("300.00"),
        occurred_on=period,
    )
    return period


def _lines(statement) -> dict:
    return {row["key"]: row for row in statement["rows"]}


def test_the_statement_reconciles(a_month_of_trading):
    """Revenue is its parts, net is revenue less expenses, gross splits in two."""
    rows = _lines(metrics.profit_and_loss(a_month_of_trading))

    assert rows["revenue"]["value"] == (
        rows["commission_earned"]["value"] + rows["other_income"]["value"]
    )
    assert rows["net"]["value"] == rows["revenue"]["value"] - rows["expenses"]["value"]
    assert rows["client_payments"]["value"] == (
        rows["reseller_cash"]["value"] + rows["upstream_direct"]["value"]
    )


def test_the_statement_excludes_the_upstream_share_from_revenue(a_month_of_trading):
    """800 collected at 20% earns 160 — the other 640 was never the reseller's."""
    rows = _lines(metrics.profit_and_loss(a_month_of_trading))
    assert rows["client_payments"]["value"] == Decimal("800.00")
    assert rows["commission_earned"]["value"] == Decimal("160.00")
    assert rows["revenue"]["value"] == Decimal("360.00")
    assert rows["net"]["value"] == Decimal("60.00")


def test_every_line_carries_the_month_before(a_month_of_trading):
    statement = metrics.profit_and_loss(a_month_of_trading)
    assert statement["prior"] == add_months(a_month_of_trading, -1)
    for row in statement["rows"]:
        assert row["delta"] == row["value"] - row["prior"]


def test_a_first_month_compares_against_zero(a_month_of_trading):
    rows = _lines(metrics.profit_and_loss(a_month_of_trading))
    assert rows["revenue"]["prior"] == Decimal("0.00")
    assert rows["revenue"]["delta"] == rows["revenue"]["value"]


def test_the_statement_keeps_its_order_and_row_kinds(db, period):
    kinds = [(row["key"], row["kind"]) for row in metrics.profit_and_loss(period)["rows"]]
    assert kinds == [
        ("client_payments", "context"),
        ("reseller_cash", "context-sub"),
        ("upstream_direct", "context-sub"),
        ("commission_earned", "line"),
        ("other_income", "line"),
        ("revenue", "subtotal"),
        ("expenses", "negative"),
        ("net", "total"),
    ]


def test_margin_is_zero_rather_than_an_error_with_no_revenue(db, period):
    statement = metrics.profit_and_loss(period)
    assert statement["margin"] == 0.0
    assert statement["prior_margin"] == 0.0


def test_expense_breakdown_shares_add_up(a_month_of_trading):
    Expense.objects.create(
        description="Rent",
        category=Expense.Category.RENT,
        amount=Decimal("100.00"),
        occurred_on=a_month_of_trading,
    )
    rows = metrics.expense_breakdown(a_month_of_trading)

    assert [row["label"] for row in rows] == ["Salary", "Rent & utilities"]  # largest first
    assert sum(row["share"] for row in rows) == pytest.approx(100.0, abs=0.2)
    assert rows[0]["share"] == 75.0


def test_expense_breakdown_uses_readable_labels(a_month_of_trading):
    """The raw choice value is `salary`; the page must not print that."""
    assert metrics.expense_breakdown(a_month_of_trading)[0]["label"] == "Salary"


def test_expense_breakdown_is_empty_for_a_quiet_month(db, period):
    assert metrics.expense_breakdown(period) == []


# ---------------------------------------------------------------------------#
# The page
# ---------------------------------------------------------------------------#


def test_the_report_renders_with_no_data_at_all(owner_client):
    """A fresh install must not divide by zero on its way to an empty report."""
    response = owner_client.get(reverse("financial_report"))
    assert response.status_code == 200
    assert response.context["statement"]["margin"] == 0.0


def test_the_report_leads_with_the_bottom_line(owner_client, a_month_of_trading):
    response = owner_client.get(reverse("financial_report"))
    body = response.content.decode()
    assert body.count('class="hero-value"') == 1
    assert response.context["net"].value == Decimal("60.00")


def test_the_current_month_has_no_next_step(owner_client):
    """There is nothing to report from the future."""
    response = owner_client.get(reverse("financial_report"))
    assert response.context["next_period"] is None
    assert "period-step disabled" in response.content.decode()


def test_a_past_month_can_step_forward(owner_client):
    past = add_months(month_start(), -3)
    response = owner_client.get(reverse("financial_report"), {"period": past.isoformat()})
    assert response.context["period"] == past
    assert response.context["next_period"] == add_months(past, 1)
    assert response.context["previous_period"] == add_months(past, -1)


def test_an_unparseable_period_falls_back_to_this_month(owner_client):
    response = owner_client.get(reverse("financial_report"), {"period": "not-a-date"})
    assert response.status_code == 200
    assert response.context["period"] == month_start()


def test_the_report_offers_print_and_export(owner_client):
    body = owner_client.get(reverse("financial_report")).content.decode()
    assert "window.print()" in body
    assert reverse("export", args=["expenses"]) in body


def test_export_is_hidden_from_a_role_that_cannot_export(client, make_user):
    client.force_login(make_user("noexport", Role.ACCOUNTANT))
    body = client.get(reverse("financial_report")).content.decode()
    assert "window.print()" in body  # printing is not gated
    assert reverse("export", args=["expenses"]) in body  # accountants may export


def test_negative_money_puts_the_sign_before_the_symbol():
    """`৳ -947.25` reads as a typo in a column of figures."""
    from apps.core.templatetags.ui import money

    assert money(Decimal("-947.25")) == "−৳ 947.25"
    assert money(Decimal("947.25")) == "৳ 947.25"
    assert money(Decimal("0")) == "৳ 0.00"
