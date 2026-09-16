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
