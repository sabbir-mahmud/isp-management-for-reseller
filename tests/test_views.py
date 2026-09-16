"""End-to-end checks through the request/response cycle."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accountants.models import Invoice, Payment
from apps.accountants.services import generate_invoices
from apps.accounts.models import Client
from apps.users.models import Role
from apps.users.roles import sync_roles
from apps.warehouse.models import Onu


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def logged_in(client, make_user):
    user = make_user("boss", Role.OWNER)
    client.force_login(user)
    return user


PAGES = [
    "dashboard",
    "financial_report",
    "client_list",
    "package_list",
    "pop_list",
    "invoice_list",
    "payment_list",
    "expense_list",
    "income_list",
    "product_list",
    "category_list",
    "onu_list",
    "movement_list",
    "staff_list",
]


@pytest.mark.parametrize("name", PAGES)
def test_every_page_renders(client, logged_in, name):
    assert client.get(reverse(name)).status_code == 200


def test_creating_a_client_also_creates_its_subscription(client, logged_in, pop, package, onu):
    response = client.post(
        reverse("client_add"),
        {
            "name": "New Client",
            "username": "newclient",
            "phone": "01712345678",
            "email": "",
            "nid": "",
            "address": "12 Road",
            "pop": pop.pk,
            "onu": onu.pk,
            "status": Client.Status.ACTIVE,
            "connection_date": "2026-09-01",
            "billing_day": 5,
            "notes": "",
            "package": package.pk,
            "monthly_price": "800.00",
            "discount": "0",
        },
    )
    assert response.status_code == 302
    created = Client.objects.get(username="newclient")
    assert created.subscription.package == package
    assert created.subscription.monthly_price == Decimal("800.00")
    # Assigning the ONU must also take it out of stock.
    onu.refresh_from_db()
    assert onu.status == Onu.Status.ASSIGNED


def test_client_form_falls_back_to_the_package_price(client, logged_in, pop, package):
    client.post(
        reverse("client_add"),
        {
            "name": "Default price",
            "username": "defprice",
            "phone": "01712345678",
            "address": "x",
            "pop": pop.pk,
            "status": Client.Status.ACTIVE,
            "connection_date": "2026-09-01",
            "billing_day": 1,
            "package": package.pk,
            "monthly_price": "",
            "discount": "",
        },
    )
    assert Client.objects.get(username="defprice").monthly_price == package.monthly_price


def test_a_discount_above_the_price_is_rejected(client, logged_in, pop, package):
    response = client.post(
        reverse("client_add"),
        {
            "name": "Bad discount",
            "username": "baddisc",
            "phone": "01712345678",
            "address": "x",
            "pop": pop.pk,
            "status": Client.Status.ACTIVE,
            "connection_date": "2026-09-01",
            "billing_day": 1,
            "package": package.pk,
            "monthly_price": "800.00",
            "discount": "900.00",
        },
    )
    assert response.status_code == 200
    assert "discount" in response.context["form"].errors
    assert not Client.objects.filter(username="baddisc").exists()


def test_search_narrows_the_client_list(client, logged_in, make_client_record):
    make_client_record(name="Findable Person", username="findme")
    make_client_record(name="Other Person", username="other")
    response = client.get(reverse("client_list"), {"q": "Findable"})
    assert [c.username for c in response.context["clients"]] == ["findme"]


def test_pagination_keeps_the_active_filter(client, logged_in, make_client_record):
    for index in range(30):
        make_client_record(name=f"Shared Name {index}", username=f"p{index}")
    response = client.get(reverse("client_list"), {"q": "Shared", "page": 2})
    assert response.status_code == 200
    assert response.context["page_obj"].number == 2
    assert response.context["paginator"].count == 30


def test_htmx_request_returns_only_the_rows(client, logged_in, make_client_record):
    make_client_record(username="htmx1")
    response = client.get(reverse("client_list"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"<html" not in response.content


def test_taking_a_payment_settles_the_invoice(client, logged_in, client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    response = client.post(
        reverse("payment_add", args=[invoice.pk]),
        {
            "amount": "800.00",
            "method": "cash",
            "received_on": "2026-09-16",
            "reference": "R1",
            "note": "",
        },
    )
    assert response.status_code == 302
    invoice.refresh_from_db()
    assert invoice.status == Invoice.Status.PAID
    assert Payment.objects.count() == 1


def test_the_payment_form_refuses_an_overpayment(client, logged_in, client_record, period):
    generate_invoices(period)
    invoice = Invoice.objects.get()
    response = client.post(
        reverse("payment_add", args=[invoice.pk]),
        {
            "amount": "5000.00",
            "method": "cash",
            "received_on": "2026-09-16",
            "reference": "",
            "note": "",
        },
    )
    assert response.status_code == 200
    assert Payment.objects.count() == 0


def test_generate_invoices_page_shows_a_preview_without_writing(client, logged_in, client_record):
    response = client.get(reverse("invoice_generate"))
    assert response.status_code == 200
    assert response.context["preview"].created_count == 1
    assert Invoice.objects.count() == 0


def test_archiving_a_client_keeps_their_invoices(client, logged_in, client_record, period):
    generate_invoices(period)
    client.post(reverse("client_delete", args=[client_record.pk]))
    assert not Client.objects.filter(pk=client_record.pk).exists()
    assert Invoice.objects.count() == 1


def test_a_package_with_subscribers_cannot_be_deleted(client, logged_in, client_record, package):
    response = client.post(reverse("package_delete", args=[package.pk]))
    assert response.status_code == 302
    assert type(package).objects.filter(pk=package.pk).exists()


def test_terminating_a_client_releases_their_onu(client, logged_in, make_client_record, onu):
    record = make_client_record(username="term", onu=onu)
    onu.status = Onu.Status.ASSIGNED
    onu.save()

    client.post(reverse("client_status", args=[record.pk]), {"status": Client.Status.TERMINATED})

    onu.refresh_from_db()
    record.refresh_from_db()
    assert onu.status == Onu.Status.IN_STOCK
    assert record.onu is None
    assert record.subscriptions.filter(status="cancelled").exists()


def test_csv_export_streams_a_file(client, logged_in, client_record):
    response = client.get(reverse("export", args=["clients"]))
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert b"Rahim Uddin" in response.content


def test_unknown_export_dataset_is_a_404(client, logged_in):
    assert client.get(reverse("export", args=["secrets"])).status_code == 404


def test_healthz_is_public_and_reports_the_database(client):
    response = client.get(reverse("healthz"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True}


def test_client_list_query_count_does_not_grow_with_rows(
    client, logged_in, make_client_record, django_assert_max_num_queries, period
):
    """Guards the annotation in `ClientQuerySet.with_related`.

    Before it, the outstanding balance was a property that queried per row, so
    this page cost one query per client on screen.
    """
    from apps.accountants.services import generate_invoices

    for index in range(20):
        make_client_record(name=f"Client {index}", username=f"q{index}")
    generate_invoices(period)

    with django_assert_max_num_queries(20):
        response = client.get(reverse("client_list"))
    assert response.status_code == 200
    assert len(response.context["clients"]) == 20


def test_settlement_page_shows_both_balances(client, logged_in, make_client_record, period):
    """A mixed base owes upstream and is owed by upstream at the same time."""
    from decimal import Decimal

    from apps.accountants.models import Invoice
    from apps.accountants.services import generate_invoices, record_payment
    from apps.core.choices import CollectionMode

    make_client_record(username="mine")
    make_client_record(username="theirs", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)
    for invoice in Invoice.objects.all():
        record_payment(invoice, invoice.total, received_on=period)

    response = client.get(reverse("settlement_list"))
    assert response.status_code == 200
    assert response.context["position"]["payable"] == Decimal("640.00")
    assert response.context["position"]["receivable"] == Decimal("160.00")


def test_recording_a_remittance_clears_the_payable(client, logged_in, client_record, period):
    from decimal import Decimal

    from apps.accountants.models import Invoice, UpstreamSettlement
    from apps.accountants.services import generate_invoices, record_payment, upstream_position

    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)

    response = client.post(
        reverse("settlement_add"),
        {
            "kind": UpstreamSettlement.Kind.REMITTANCE,
            "amount": "640.00",
            "period": period.isoformat(),
            "settled_on": period.isoformat(),
            "reference": "REM-1",
            "note": "",
        },
    )
    assert response.status_code == 302
    assert upstream_position()["payable"] == Decimal("0.00")


def test_the_client_form_accepts_a_collection_mode_override(client, logged_in, pop, package):
    from apps.core.choices import CollectionMode

    client.post(
        reverse("client_add"),
        {
            "name": "Online payer",
            "username": "onlinepayer",
            "phone": "01712345678",
            "address": "x",
            "pop": pop.pk,
            "status": Client.Status.ACTIVE,
            "collection_mode": CollectionMode.UPSTREAM,
            "connection_date": "2026-09-01",
            "billing_day": 1,
            "package": package.pk,
            "monthly_price": "800.00",
            "discount": "0",
            "commission_percent": "25.00",
        },
    )
    created = Client.objects.get(username="onlinepayer")
    assert created.effective_collection_mode == CollectionMode.UPSTREAM
    assert created.subscription.effective_commission_percent == Decimal("25.00")
