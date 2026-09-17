"""Billing settings: the page, its previews' inputs, and its validation."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accountants.models import BillingSettings, Invoice
from apps.core.choices import CollectionMode
from apps.users.models import Role
from apps.users.roles import sync_roles


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("settingsboss", Role.OWNER))
    return client


def _payload(**overrides):
    data = {
        "collection_mode": CollectionMode.RESELLER,
        "upstream_name": "Link3",
        "commission_percent": "20.00",
        "invoice_prefix": "INV",
        "due_days": 10,
        "auto_generate": "on",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def test_saving_stays_on_the_settings_page(owner_client):
    response = owner_client.post(
        reverse("billing_settings"), _payload(commission_percent="25", invoice_prefix=" bill ")
    )
    assert response.status_code == 302
    assert response.url == reverse("billing_settings")

    row = BillingSettings.load()  # the cache was cleared on save
    assert row.commission_percent == Decimal("25.00")
    assert row.invoice_prefix == "BILL"


@pytest.mark.parametrize("prefix", ["IN-V", "IN V", "ইনভ"])
def test_the_prefix_is_letters_and_digits(owner_client, prefix):
    response = owner_client.post(reverse("billing_settings"), _payload(invoice_prefix=prefix))
    assert response.status_code == 200
    assert "invoice_prefix" in response.context["form"].errors


def test_due_days_are_capped(owner_client):
    response = owner_client.post(reverse("billing_settings"), _payload(due_days=365))
    assert "due_days" in response.context["form"].errors


def test_upstream_collection_needs_the_operators_name(owner_client):
    response = owner_client.post(
        reverse("billing_settings"),
        _payload(collection_mode=CollectionMode.UPSTREAM, upstream_name=""),
    )
    assert "upstream_name" in response.context["form"].errors

    response = owner_client.post(
        reverse("billing_settings"),
        _payload(collection_mode=CollectionMode.UPSTREAM, upstream_name="Link3"),
    )
    assert response.status_code == 302


def test_the_page_shows_how_far_the_defaults_reach(owner_client, make_client_record, period):
    from apps.accountants.services import generate_invoices

    make_client_record(username="follows")
    make_client_record(username="own", collection_mode=CollectionMode.UPSTREAM)
    generate_invoices(period)

    context = owner_client.get(reverse("billing_settings")).context
    reach = context["reach"]
    assert reach["clients"] == {"total": 2, "following": 1, "overridden": 1}
    assert reach["invoices"] == 2

    # Two invoices exist this month, so the preview continues at 0003.
    assert context["numbering"]["next_sequence"] == 3
    assert context["numbering"]["saved_prefix"] == "INV"
    assert Invoice.objects.count() == 2


def test_the_settings_form_is_sectioned_with_previews(owner_client):
    body = owner_client.get(reverse("billing_settings")).content.decode()
    assert "is-sectioned" in body
    assert body.count('class="choice-tile"') == 2
    assert "data-split-preview" in body
    assert 'data-next-sequence="1"' in body
    assert "Save settings" in body
