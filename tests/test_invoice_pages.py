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
