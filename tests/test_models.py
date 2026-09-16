"""Model-level guarantees: constraints, derived values and soft deletion."""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Client, Subscription
from apps.warehouse.models import Product, StockMovement


def test_client_code_is_assigned_and_unique(make_client_record):
    first = make_client_record(name="A", username="a1")
    second = make_client_record(name="B", username="b1")
    assert first.client_code.startswith("C-")
    assert first.client_code != second.client_code


def test_client_soft_delete_keeps_the_row(client_record):
    pk = client_record.pk
    client_record.delete()
    assert not Client.objects.filter(pk=pk).exists()
    assert Client.all_objects.filter(pk=pk).exists()
    assert Client.all_objects.get(pk=pk).deleted_at is not None


def test_client_restore_brings_it_back(client_record):
    client_record.delete()
    Client.all_objects.get(pk=client_record.pk).restore()
    assert Client.objects.filter(pk=client_record.pk).exists()


def test_billing_day_outside_range_is_rejected(pop):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Client.objects.create(
                name="Bad day",
                username="badday",
                phone="01712345678",
                address="x",
                pop=pop,
                billing_day=31,
            )


def test_only_one_active_subscription_per_client(client_record, package):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Subscription.objects.create(
                client=client_record,
                package=package,
                monthly_price=Decimal("800.00"),
                status=Subscription.Status.ACTIVE,
            )


def test_subscription_net_monthly_applies_discount(make_client_record):
    record = make_client_record(username="disc", price="800.00", discount="50.00")
    assert record.subscription.net_monthly == Decimal("750.00")


def test_subscription_covers_respects_start_and_end(client_record):
    subscription = client_record.subscription
    today = timezone.localdate().replace(day=1)
    assert subscription.covers(today)
    subscription.cancel(when=today.replace(day=28))
    assert subscription.covers(today)


def test_product_quantity_is_the_sum_of_its_movements(product):
    StockMovement.objects.create(product=product, kind=StockMovement.Kind.IN, quantity=100)
    StockMovement.objects.create(product=product, kind=StockMovement.Kind.OUT, quantity=30)
    StockMovement.objects.create(product=product, kind=StockMovement.Kind.ADJUST, quantity=-5)
    assert Product.objects.get(pk=product.pk).quantity == 65


def test_low_stock_flags_items_at_reorder_level(product):
    StockMovement.objects.create(product=product, kind=StockMovement.Kind.IN, quantity=5)
    assert Product.objects.get(pk=product.pk).is_low is True
    assert Product.objects.low_stock().count() == 1
