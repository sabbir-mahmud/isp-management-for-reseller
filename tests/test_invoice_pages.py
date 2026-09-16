"""Invoice list, detail and form: sorting, chips, and the form's starting values."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accountants.models import Invoice
from apps.accountants.services import cancel_invoice, generate_invoices, record_payment
from apps.users.models import Role
from apps.users.roles import sync_roles


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("billboss", Role.OWNER))
    return client


@pytest.fixture
def two_invoices(make_client_record, period):
    make_client_record(name="Settled Up", username="paid1")
    make_client_record(name="In Arrears", username="owes1")
    generate_invoices(period)
    record_payment(Invoice.objects.get(client__username="paid1"), Decimal("800.00"))
    return Invoice.objects.get(client__username="paid1"), Invoice.objects.get(
        client__username="owes1"
    )


def _clients(response):
    return [invoice.client.name for invoice in response.context["invoices"]]


def test_invoices_sort_by_client(owner_client, two_invoices):
    response = owner_client.get(reverse("invoice_list"), {"sort": "client"})
    assert _clients(response) == ["In Arrears", "Settled Up"]


def test_invoices_sort_by_what_is_still_owed(owner_client, two_invoices):
    response = owner_client.get(reverse("invoice_list"), {"sort": "-owing"})
    assert _clients(response)[0] == "In Arrears"


def test_an_unknown_invoice_sort_key_is_ignored(owner_client, two_invoices):
    response = owner_client.get(reverse("invoice_list"), {"sort": "client__nid"})
    assert response.status_code == 200
    assert response.context["sort"] == ""


def test_status_chips_count_every_invoice_and_filter(owner_client, two_invoices):
    paid, owing = two_invoices
    cancel_invoice(owing)

    response = owner_client.get(reverse("invoice_list"), {"status": "paid"})
    chips = {chip.label: chip for chip in response.context["chips"]}

    assert chips["All invoices"].value == 2
    assert chips["Paid"].value == 1 and chips["Paid"].is_active
    assert chips["Cancelled"].value == 1
    assert _clients(response) == ["Settled Up"]


def test_the_summary_describes_the_filtered_rows(owner_client, two_invoices):
    totals = owner_client.get(reverse("invoice_list"), {"status": "paid"}).context["totals"]
    assert totals["billed"] == Decimal("800.00")
    assert totals["paid_percent"] == 100


def test_detail_shows_how_much_is_paid(owner_client, two_invoices):
    paid, owing = two_invoices
    assert owner_client.get(paid.get_absolute_url()).context["paid_percent"] == 100

    response = owner_client.get(owing.get_absolute_url())
    assert response.context["paid_percent"] == 0
    assert response.context["commission_percent"] + response.context["upstream_percent"] == 100


def test_a_cancelled_invoice_offers_no_payment(owner_client, two_invoices):
    _, owing = two_invoices
    cancel_invoice(owing)
    body = owner_client.get(owing.get_absolute_url()).content.decode()
    assert reverse("payment_add", args=[owing.pk]) not in body


def test_new_invoice_starts_from_the_billing_settings(owner_client, period):
    initial = owner_client.get(reverse("invoice_add")).context["form"].initial
    assert initial["period"] == period
    assert initial["commission_percent"] == Decimal("20.00")
    assert (initial["due_date"] - initial["issue_date"]).days == 10


def test_new_invoice_for_a_client_starts_from_their_plan(owner_client, make_client_record):
    record = make_client_record(price="950.00", discount="50.00")
    initial = (
        owner_client.get(reverse("invoice_add"), {"client": record.pk}).context["form"].initial
    )

    assert initial["client"] == record.pk
    assert initial["subtotal"] == Decimal("950.00")
    assert initial["discount"] == Decimal("50.00")


def test_a_bad_client_parameter_is_ignored(owner_client):
    response = owner_client.get(reverse("invoice_add"), {"client": "nope"})
    assert response.status_code == 200
    assert "client" not in response.context["form"].initial


def test_the_invoice_form_is_sectioned(owner_client):
    body = owner_client.get(reverse("invoice_add")).content.decode()
    assert "is-sectioned" in body
    assert "Bill to" in body


# ---------------------------------------------------------------------------#
# Taking a payment
# ---------------------------------------------------------------------------#


def test_the_payment_page_shows_the_bill_and_method_tiles(owner_client, two_invoices):
    _, owing = two_invoices
    response = owner_client.get(reverse("payment_add", args=[owing.pk]))
    body = response.content.decode()

    assert response.status_code == 200
    assert owing.number in body
    assert 'class="choice-tile"' in body
    assert 'data-fill="800.00"' in body
    assert response.context["submit_label"] == "Record payment"


def test_the_payment_note_is_kept(owner_client, two_invoices):
    _, owing = two_invoices
    owner_client.post(
        reverse("payment_add", args=[owing.pk]),
        {"amount": "300.00", "method": "bkash", "received_on": "2026-09-16", "note": "Half now"},
    )
    payment = owing.payments.get()
    assert payment.note == "Half now"
    assert payment.method == "bkash"


def test_a_paid_invoice_sends_you_back_to_it(owner_client, two_invoices):
    paid, _ = two_invoices
    response = owner_client.get(reverse("payment_add", args=[paid.pk]))
    assert response.status_code == 302
    assert response.url == paid.get_absolute_url()


def test_a_cancelled_invoice_sends_you_back_to_it(owner_client, two_invoices):
    _, owing = two_invoices
    cancel_invoice(owing)
    response = owner_client.get(reverse("payment_add", args=[owing.pk]))
    assert response.status_code == 302


def test_amount_shortcuts_lead_with_the_balance_and_stay_under_it(two_invoices):
    from apps.accountants.views import amount_shortcuts

    _, owing = two_invoices  # 800 due, on an 800 plan
    values = [shortcut["value"] for shortcut in amount_shortcuts(owing)]

    assert values[0] == Decimal("800.00")
    # The monthly fee equals the balance, so it is not offered twice.
    assert values[1:] == [Decimal("500"), Decimal("400.00")]


def test_a_settled_invoice_offers_no_shortcuts(two_invoices):
    from apps.accountants.views import amount_shortcuts

    paid, _ = two_invoices
    assert amount_shortcuts(paid) == []


# ---------------------------------------------------------------------------#
# Payments list
# ---------------------------------------------------------------------------#


@pytest.fixture
def two_payments(make_client_record, period):
    from datetime import timedelta

    from django.utils import timezone

    make_client_record(name="Today Payer", username="today1")
    make_client_record(name="Old Payer", username="old1")
    generate_invoices(period)
    today = timezone.localdate()
    record_payment(
        Invoice.objects.get(client__username="today1"), Decimal("800.00"), received_on=today
    )
    record_payment(
        Invoice.objects.get(client__username="old1"),
        Decimal("300.00"),
        received_on=today - timedelta(days=40),
        method="bkash",
    )


def test_payments_can_be_found_by_client_code(owner_client, two_payments):
    """The client page links here with `?q=<client code>`."""
    code = Invoice.objects.get(client__username="old1").client.client_code
    response = owner_client.get(reverse("payment_list"), {"q": code})
    assert [p.client.name for p in response.context["payments"]] == ["Old Payer"]


def test_the_today_chip_filters_to_today(owner_client, two_payments):
    response = owner_client.get(reverse("payment_list"), {"when": "today"})
    chips = {chip.label: chip for chip in response.context["chips"]}

    assert [p.client.name for p in response.context["payments"]] == ["Today Payer"]
    assert chips["Today"].is_active
    assert chips["All time"].value == "৳ 1,100.00"
    assert response.context["totals"]["gross"] == Decimal("800.00")


def test_payments_are_grouped_by_day_only_in_date_order(owner_client, two_payments):
    response = owner_client.get(reverse("payment_list"))
    assert response.context["group_by_day"]
    assert response.context["payments"][0].day_total == Decimal("800.00")
    assert b"day-row" in response.content

    response = owner_client.get(reverse("payment_list"), {"sort": "-amount"})
    assert not response.context["group_by_day"]
    assert b"day-row" not in response.content


def test_a_date_range_shows_as_one_removable_pill(owner_client, two_payments):
    body = owner_client.get(
        reverse("payment_list"), {"received_on_min": "2026-01-01", "received_on_max": ""}
    ).content.decode()
    assert "Received between" in body
    assert "2026-01-01 – …" in body
    assert 'class="btn-reset"' in body


# ---------------------------------------------------------------------------#
# Upstream
# ---------------------------------------------------------------------------#


@pytest.fixture
def mixed_base(make_client_record, period):
    """One client pays you, one pays upstream; both paid in full this month."""
    from apps.core.choices import CollectionMode

    make_client_record(username="mine")
    make_client_record(username="theirs", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)
    for invoice in Invoice.objects.all():
        record_payment(invoice, invoice.total, received_on=period)


def test_the_monthly_breakdown_agrees_with_the_single_month_position(mixed_base, period):
    from apps.accountants.models import UpstreamSettlement
    from apps.accountants.services import record_settlement, upstream_months, upstream_position
    from apps.core.utils import add_months

    record_settlement(UpstreamSettlement.Kind.REMITTANCE, Decimal("400.00"), period=period)
    record_settlement(
        UpstreamSettlement.Kind.COMMISSION_PAYOUT, Decimal("60.00"), period=add_months(period, -1)
    )

    months = upstream_months(3)
    assert [row["period"] for row in months] == [
        period,
        add_months(period, -1),
        add_months(period, -2),
    ]
    for row in months:
        single = upstream_position(row["period"])
        assert {key: row[key] for key in single if key != "period"} == {
            key: value for key, value in single.items() if key != "period"
        }
    assert months[0]["payable"] == Decimal("240.00")
    assert months[1]["receivable"] == Decimal("-60.00")


def test_the_upstream_page_nets_the_two_balances(owner_client, mixed_base):
    response = owner_client.get(reverse("settlement_list"))
    position = response.context["position"]

    assert response.status_code == 200
    assert position["net"] == Decimal("480.00")  # 640 to remit, less 160 to come
    assert position["remitted_percent"] == 0
    assert response.context["arrangement"]["reseller"] == 1
    assert response.context["arrangement"]["upstream"] == 1
    assert b"kind=remittance&amount=640.00" in response.content


def test_settle_links_prefill_the_settlement_form(owner_client):
    initial = (
        owner_client.get(
            reverse("settlement_add"),
            {"kind": "remittance", "period": "2026-07-15", "amount": "640.5"},
        )
        .context["form"]
        .initial
    )
    assert initial["kind"] == "remittance"
    assert str(initial["period"]) == "2026-07-01"
    assert initial["amount"] == Decimal("640.50")


@pytest.mark.parametrize("amount", ["abc", "-5", "NaN", "Infinity", ""])
def test_a_bad_settle_amount_is_ignored(owner_client, amount):
    response = owner_client.get(reverse("settlement_add"), {"amount": amount, "kind": "bogus"})
    assert response.status_code == 200
    assert "amount" not in response.context["form"].initial
    assert "kind" not in response.context["form"].initial


def test_the_month_filter_accepts_what_a_month_input_sends(owner_client, two_invoices, period):
    """`<input type="month">` posts YYYY-MM; that used to be rejected and ignored."""
    from apps.core.utils import add_months

    this_month = owner_client.get(reverse("invoice_list"), {"period": f"{period:%Y-%m}"})
    last_month = owner_client.get(
        reverse("invoice_list"), {"period": f"{add_months(period, -1):%Y-%m}"}
    )
    assert len(this_month.context["invoices"]) == 2
    assert len(last_month.context["invoices"]) == 0


# ---------------------------------------------------------------------------#
# Expenses
# ---------------------------------------------------------------------------#


@pytest.fixture
def some_expenses(db, period):
    from apps.accountants.models import Expense
    from apps.core.utils import add_months

    last_month = add_months(period, -1)
    Expense.objects.create(
        description="Bandwidth bill", category="bandwidth", amount="600", occurred_on=period
    )
    Expense.objects.create(
        description="Tech salary",
        category="salary",
        amount="300",
        occurred_on=period,
        note="Rahim, September",
    )
    Expense.objects.create(
        description="Old salary", category="salary", amount="450", occurred_on=last_month
    )


def test_expenses_compare_this_month_with_last(owner_client, some_expenses):
    context = owner_client.get(reverse("expense_list")).context
    assert context["this_month"] == Decimal("900.00")
    assert context["last_month"] == Decimal("450.00")
    assert context["month_delta"] > 0
    assert context["month_delta_percent"] == 100
    assert len(context["trend"]) == 6


def test_the_category_breakdown_follows_the_search_and_toggles(owner_client, some_expenses):
    context = owner_client.get(reverse("expense_list"), {"when": "month"}).context
    breakdown = {row["category"]: row for row in context["breakdown"]}

    assert breakdown["bandwidth"]["total"] == Decimal("600.00")
    assert breakdown["salary"]["total"] == Decimal("300.00")  # last month's is outside
    assert breakdown["bandwidth"]["share"] == 67
    assert "category=salary" in breakdown["salary"]["url"]

    context = owner_client.get(reverse("expense_list"), {"category": "salary"}).context
    (salary,) = context["breakdown"]
    assert salary["is_active"]
    assert "category" not in salary["url"]  # clicking it again clears the filter


def test_expense_search_covers_the_note(owner_client, some_expenses):
    response = owner_client.get(reverse("expense_list"), {"description": "rahim"})
    assert [e.description for e in response.context["expenses"]] == ["Tech salary"]


def test_expenses_are_grouped_by_month_in_date_order(owner_client, some_expenses):
    response = owner_client.get(reverse("expense_list"))
    assert response.context["group_by_month"]
    assert response.content.count(b'class="day-row"') == 2
    assert response.context["expenses"][0].month_total == Decimal("900.00")

    response = owner_client.get(reverse("expense_list"), {"sort": "amount"})
    assert b'class="day-row"' not in response.content


def test_the_expense_form_is_sectioned_with_category_tiles(owner_client):
    body = owner_client.get(reverse("expense_add")).content.decode()
    assert "is-sectioned" in body
    assert body.count('class="choice-tile"') == 6
    assert 'class="input-prefix"' in body


# ---------------------------------------------------------------------------#
# Toolbar
# ---------------------------------------------------------------------------#


def _range_group(body):
    import re

    return re.search(r'<div class="toolbar-field toolbar-range"[^>]*>', body).group(0)


def test_the_expense_date_range_waits_for_custom(owner_client, some_expenses):
    body = owner_client.get(reverse("expense_list")).content.decode()
    assert "hidden" in _range_group(body)
    assert 'value="custom"' in body  # offered in the Period select

    body = owner_client.get(reverse("expense_list"), {"when": "custom"}).content.decode()
    assert "hidden" not in _range_group(body)


def test_a_range_in_the_url_is_shown_even_without_custom(owner_client, some_expenses, period):
    import re

    body = owner_client.get(
        reverse("expense_list"), {"occurred_on_min": f"{period:%Y-%m-%d}"}
    ).content.decode()
    assert "hidden" not in _range_group(body)
    assert re.search(rf'name="occurred_on_min"\s+value="{period:%Y-%m-%d}"', body)


def test_custom_period_has_no_pill_of_its_own(owner_client, some_expenses, period):
    response = owner_client.get(
        reverse("expense_list"), {"when": "custom", "occurred_on_min": f"{period:%Y-%m-%d}"}
    )
    body = response.content.decode()
    assert "Custom dates" not in body.split('class="toolbar-status"')[1]
    assert "Dates" in body.split('class="toolbar-status"')[1]
    # Custom filters nothing itself: the range alone decides.
    assert len(response.context["expenses"]) == 2


def test_ranges_without_a_trigger_are_always_shown(owner_client, two_payments):
    body = owner_client.get(reverse("payment_list")).content.decode()
    assert "hidden" not in _range_group(body)
    assert "data-range-for" not in _range_group(body)


def test_a_new_search_keeps_the_sort(owner_client, some_expenses):
    body = owner_client.get(reverse("expense_list"), {"sort": "-amount"}).content.decode()
    assert '<input type="hidden" name="sort" value="-amount">' in body


# ---------------------------------------------------------------------------#
# Other income (shares the ledger page with expenses)
# ---------------------------------------------------------------------------#


@pytest.fixture
def some_income(db, period):
    from apps.accountants.models import Income
    from apps.core.utils import add_months

    Income.objects.create(
        description="Fibre install", source="installation", amount="1500", occurred_on=period
    )
    Income.objects.create(
        description="ONU sold",
        source="hardware",
        amount="500",
        occurred_on=period,
        note="Karim, spare unit",
    )
    Income.objects.create(
        description="Old repair",
        source="service",
        amount="1000",
        occurred_on=add_months(period, -1),
    )


def test_income_uses_the_ledger_page(owner_client, some_income):
    response = owner_client.get(reverse("income_list"))
    context = response.context

    assert response.status_code == 200
    assert context["ledger"]["total_label"] == "Received"
    assert context["totals"]["sum_total"] == Decimal("3000.00")
    assert context["this_month"] == Decimal("2000.00")
    assert context["trend"][-1]["income"] == Decimal("2000.00")
    assert context["group_by_month"]
    # More income than last month is good news, so it is coloured as such.
    assert b"delta-good" in response.content
    assert b"not here" in response.content  # the subscription warning


def test_income_breaks_down_by_source(owner_client, some_income):
    context = owner_client.get(reverse("income_list"), {"when": "month"}).context
    breakdown = {row["key"]: row for row in context["breakdown"]}
    assert set(breakdown) == {"installation", "hardware"}
    assert breakdown["installation"]["share"] == 75
    assert "source=hardware" in breakdown["hardware"]["url"]


def test_income_sorts_by_source_and_searches_notes(owner_client, some_income):
    response = owner_client.get(reverse("income_list"), {"sort": "kind"})
    assert [i.source for i in response.context["incomes"]] == [
        "hardware",
        "installation",
        "service",
    ]
    assert not response.context["group_by_month"]

    response = owner_client.get(reverse("income_list"), {"description": "karim"})
    assert [i.description for i in response.context["incomes"]] == ["ONU sold"]


def test_more_spending_is_coloured_as_bad_news(owner_client, some_expenses):
    assert b"delta-bad" in owner_client.get(reverse("expense_list")).content


def test_the_income_form_is_sectioned_with_source_tiles(owner_client):
    body = owner_client.get(reverse("income_add")).content.decode()
    assert "is-sectioned" in body
    assert body.count('class="choice-tile"') == 4
    assert "Received on" in body
    assert "Record income" in body


def test_the_htmx_rows_render_for_both_ledgers(owner_client, some_income, some_expenses):
    for name in ("income_list", "expense_list"):
        response = owner_client.get(reverse(name), HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert b"<html" not in response.content
        assert b"category-tag" in response.content
