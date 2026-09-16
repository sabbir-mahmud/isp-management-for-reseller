"""Fill an empty database with believable data, for demos and manual testing.

Refuses to run against a database that already has clients unless forced, so
it cannot be pointed at production by accident.
"""

import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accountants.models import (
    BillingSettings,
    Expense,
    Income,
    Payment,
    UpstreamSettlement,
)
from apps.accountants.services import (
    generate_invoices,
    record_payment,
    record_settlement,
    upstream_position,
)
from apps.accounts.models import Client, Package, Subscription
from apps.core.choices import CollectionMode
from apps.core.utils import add_months, month_start
from apps.users.models import Profile, Role
from apps.warehouse.models import Category, Onu, Pop, Product, StockMovement

User = get_user_model()

FIRST = [
    "Rahim",
    "Karim",
    "Shahin",
    "Nusrat",
    "Tanvir",
    "Farhana",
    "Imran",
    "Sadia",
    "Rakib",
    "Mitu",
    "Jashim",
    "Sumaiya",
    "Arif",
    "Nadia",
    "Babul",
    "Rupa",
]
LAST = ["Uddin", "Hossain", "Akter", "Islam", "Rahman", "Chowdhury", "Khan", "Sarker"]
AREAS = ["Kaliganj Bazar", "Station Road", "College Para", "Mollik Para", "Noyapara"]


class Command(BaseCommand):
    help = "Create demo clients, packages, inventory, invoices and payments."

    def add_arguments(self, parser):
        parser.add_argument("--clients", type=int, default=60)
        parser.add_argument("--months", type=int, default=6, help="Months of billing history.")
        parser.add_argument("--force", action="store_true", help="Run even if data exists.")

    @transaction.atomic
    def handle(self, *args, **options):
        if Client.objects.exists() and not options["force"]:
            raise CommandError(
                "This database already has clients. Re-run with --force if you are sure."
            )

        random.seed(42)  # Reproducible demos.
        self._billing_settings()
        self._staff()
        pops = self._pops()
        packages = self._packages()
        onus = self._inventory()
        self._clients(options["clients"], pops, packages, onus)
        self._billing_history(options["months"])

        position = upstream_position()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Client.objects.count()} clients, "
                f"{Package.objects.count()} packages, {Onu.objects.count()} ONUs, "
                f"{Payment.objects.count()} payments, "
                f"{UpstreamSettlement.objects.count()} settlements."
            )
        )
        mix = Client.objects.filter(collection_mode=CollectionMode.UPSTREAM).count()
        self.stdout.write(
            f"{Client.objects.count() - mix} client(s) pay you, {mix} pay the upstream operator."
        )
        self.stdout.write(
            f"Upstream position: {position['payable']} to remit, "
            f"{position['receivable']} commission receivable."
        )
        self.stdout.write(
            "Staff logins (password: demopass123): owner, manager, accountant, support"
        )

    def _billing_settings(self):
        settings_row = BillingSettings.load()
        settings_row.collection_mode = CollectionMode.RESELLER
        settings_row.upstream_name = "Metro Broadband"
        settings_row.commission_percent = Decimal("20.00")
        settings_row.save()

    def _staff(self):
        for username, role in [
            ("owner", Role.OWNER),
            ("manager", Role.MANAGER),
            ("accountant", Role.ACCOUNTANT),
            ("support", Role.SUPPORT),
        ]:
            user, created = User.objects.get_or_create(
                username=username, defaults={"email": f"{username}@example.com"}
            )
            if created:
                user.set_password("demopass123")
                user.is_staff = role == Role.OWNER
                user.save()
            Profile.objects.update_or_create(user=user, defaults={"role": role})

    def _pops(self):
        main = Pop.objects.create(name="Main POP", code="MAIN", address="Kaliganj HQ")
        return [main] + [
            Pop.objects.create(name=f"{area} POP", code=area[:4].upper(), parent=main, address=area)
            for area in AREAS[:3]
        ]

    def _packages(self):
        # The upstream operator pays a better rate on the faster plans, which
        # is why the commission override on a package is worth having.
        rows = [
            ("Starter 10", 10, 5, 5, "500.00", None),
            ("Home 20", 20, 10, 10, "800.00", None),
            ("Home 30", 30, 15, 15, "1100.00", "22.50"),
            ("Pro 50", 50, 25, 25, "1800.00", "25.00"),
        ]
        return [
            Package.objects.create(
                name=name,
                bandwidth_mbps=speed,
                ggc_mbps=ggc,
                fna_mbps=fna,
                monthly_price=Decimal(price),
                commission_percent=Decimal(commission) if commission else None,
            )
            for name, speed, ggc, fna, price, commission in rows
        ]

    def _inventory(self):
        category = Category.objects.create(name="Networking", description="Cables and routers")
        for name, price, qty in [("Drop wire (100m)", "1200.00", 40), ("Patch cord", "80.00", 150)]:
            product = Product.objects.create(
                name=name, category=category, unit_price=Decimal(price), reorder_level=10
            )
            StockMovement.objects.create(
                product=product, kind=StockMovement.Kind.IN, quantity=qty, reason="Opening stock"
            )
        return [
            Onu.objects.create(
                serial=f"ONU{20250000 + index}",
                model=random.choice(["VSOL V2802", "CDATA 72GW", "Huawei HG8310"]),
                purchase_price=Decimal("1500.00"),
            )
            for index in range(80)
        ]

    def _clients(self, count, pops, packages, onus):
        today = timezone.localdate()
        for index in range(count):
            package = random.choices(packages, weights=[3, 5, 3, 1])[0]
            status = random.choices(
                [Client.Status.ACTIVE, Client.Status.SUSPENDED, Client.Status.TERMINATED],
                weights=[88, 8, 4],
            )[0]
            # About a third of the base pays the upstream portal online; the
            # rest still pays the reseller at the counter.
            mode = CollectionMode.UPSTREAM if random.random() < 0.35 else CollectionMode.RESELLER
            client = Client.objects.create(
                name=f"{random.choice(FIRST)} {random.choice(LAST)}",
                collection_mode=mode,
                username=f"user{1000 + index}",
                phone=f"01{random.randint(3, 9)}{random.randint(10000000, 99999999)}",
                email=f"client{index}@example.com" if index % 3 == 0 else "",
                nid=str(random.randint(1000000000, 9999999999)),
                address=f"{random.randint(1, 99)} {random.choice(AREAS)}",
                pop=random.choice(pops),
                onu=onus[index] if index < len(onus) else None,
                status=status,
                connection_date=add_months(today, -random.randint(0, 18)),
                billing_day=random.choice([1, 5, 10, 15]),
            )
            if client.onu:
                Onu.objects.filter(pk=client.onu_id).update(status=Onu.Status.ASSIGNED)
            Subscription.objects.create(
                client=client,
                package=package,
                monthly_price=package.monthly_price,
                discount=Decimal("50.00") if index % 11 == 0 else Decimal("0.00"),
                start_date=client.connection_date,
                status=(
                    Subscription.Status.CANCELLED
                    if status == Client.Status.TERMINATED
                    else Subscription.Status.ACTIVE
                ),
                end_date=today if status == Client.Status.TERMINATED else None,
            )

    def _billing_history(self, months):
        """Bill each past month and collect most of it, so reports have shape."""
        owner = User.objects.filter(username="owner").first()
        base = month_start()
        for offset in range(months - 1, -1, -1):
            period = add_months(base, -offset)
            result = generate_invoices(period, actor=owner)
            for invoice in result.created:
                roll = random.random()
                if roll < 0.75:
                    amount = invoice.amount_due
                elif roll < 0.9:
                    amount = (invoice.amount_due / 2).quantize(Decimal("0.01"))
                else:
                    continue  # Left unpaid, which is what aging reports are for.
                if invoice.collected_by_reseller:
                    method = random.choice(
                        [Payment.Method.CASH, Payment.Method.BKASH, Payment.Method.NAGAD]
                    )
                else:
                    method = Payment.Method.ONLINE
                record_payment(
                    invoice,
                    amount,
                    method=method,
                    received_on=invoice.due_date,
                    actor=owner,
                )

            # The upstream operator's share is *not* seeded as an expense: it
            # flows through `UpstreamSettlement` below, and booking it in both
            # places would deduct the same money twice — the exact mistake the
            # settlement screen warns about.
            for description, category, low, high in [
                ("Staff salary", Expense.Category.SALARY, 4000, 6000),
                ("Office rent & utilities", Expense.Category.RENT, 1500, 2500),
                ("Line maintenance", Expense.Category.MAINTENANCE, 500, 1800),
            ]:
                Expense.objects.create(
                    description=description,
                    category=category,
                    amount=Decimal(random.randint(low, high)),
                    occurred_on=period,
                    created_by=owner,
                )
            Income.objects.create(
                description="New installation fees",
                source=Income.Source.INSTALLATION,
                amount=Decimal(random.randint(1500, 6000)),
                occurred_on=period,
                created_by=owner,
            )

            # Settle most of each month with the upstream operator, leaving the
            # newest month open so the outstanding position is visible.
            if offset == 0:
                continue
            position = upstream_position(period)
            if position["payable"] > 0:
                record_settlement(
                    UpstreamSettlement.Kind.REMITTANCE,
                    position["payable"],
                    period=period,
                    settled_on=add_months(period, 1),
                    reference=f"REM-{period:%Y%m}",
                    actor=owner,
                )
            if position["receivable"] > 0:
                record_settlement(
                    UpstreamSettlement.Kind.COMMISSION_PAYOUT,
                    position["receivable"],
                    period=period,
                    settled_on=add_months(period, 1),
                    reference=f"COM-{period:%Y%m}",
                    actor=owner,
                )
