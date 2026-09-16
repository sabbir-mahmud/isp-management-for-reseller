"""Shared fixtures.

Factories are plain functions rather than factory_boy classes: the models
carry real constraints and derived fields, so building through the ORM is
both simpler to read and a better test of the model itself.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from apps.accountants.models import BillingSettings
from apps.accounts.models import Client, Package, Subscription
from apps.core.utils import month_start
from apps.users.models import Profile, Role
from apps.warehouse.models import Category, Onu, Pop, Product

User = get_user_model()


@pytest.fixture(autouse=True)
def _billing_settings(db):
    """Every test gets the singleton with predictable values.

    The row is cached in production, so the cache is cleared around each test
    — otherwise one test's settings would survive another's rollback.
    """
    cache.delete(BillingSettings.CACHE_KEY)
    row = BillingSettings.objects.update_or_create(
        pk=1,
        defaults={"commission_percent": Decimal("20.00"), "due_days": 10, "invoice_prefix": "INV"},
    )[0]
    yield row
    cache.delete(BillingSettings.CACHE_KEY)


@pytest.fixture
def make_user(db):
    def _make(username="tester", role=Role.OWNER, password="testpass123", **kwargs):
        user = User.objects.create_user(username=username, password=password, **kwargs)
        Profile.objects.update_or_create(user=user, defaults={"role": role})
        return user

    return _make


@pytest.fixture
def owner(make_user):
    return make_user("owner", Role.OWNER)


@pytest.fixture
def pop(db):
    return Pop.objects.create(name="Main POP", code="MAIN")


@pytest.fixture
def package(db):
    return Package.objects.create(
        name="Home 20",
        bandwidth_mbps=20,
        ggc_mbps=10,
        fna_mbps=10,
        monthly_price=Decimal("800.00"),
    )


@pytest.fixture
def onu(db):
    return Onu.objects.create(serial="ONU-0001", model="VSOL", purchase_price=Decimal("1500.00"))


@pytest.fixture
def make_client_record(db, pop, package):
    def _make(
        name="Rahim Uddin", status=Client.Status.ACTIVE, price=None, discount="0.00", **kwargs
    ):
        record = Client.objects.create(
            name=name,
            username=kwargs.pop("username", f"user{Client.all_objects.count() + 1}"),
            phone=kwargs.pop("phone", "01712345678"),
            address="12 Station Road",
            pop=pop,
            status=status,
            billing_day=kwargs.pop("billing_day", 1),
            **kwargs,
        )
        Subscription.objects.create(
            client=record,
            package=package,
            monthly_price=Decimal(price) if price else package.monthly_price,
            discount=Decimal(discount),
            start_date=kwargs.get("connection_date") or timezone.localdate().replace(day=1),
        )
        return record

    return _make


@pytest.fixture
def client_record(make_client_record):
    return make_client_record()


@pytest.fixture
def product(db):
    category = Category.objects.create(name="Networking")
    return Product.objects.create(
        name="Patch cord", category=category, unit_price=Decimal("80.00"), reorder_level=5
    )


@pytest.fixture
def period():
    return month_start()
