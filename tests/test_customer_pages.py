"""Clients, packages and POPs: sorting, filtering and the aggregates on show."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.models import Client, Package, Subscription
from apps.users.models import Role
from apps.users.roles import sync_roles
from apps.warehouse.models import Pop


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("custboss", Role.OWNER))
    return client


def _names(response, key="clients"):
    return [obj.name for obj in response.context[key]]


# ---------------------------------------------------------------------------#
# Sorting
# ---------------------------------------------------------------------------#


def test_clients_sort_by_name(owner_client, make_client_record):
    make_client_record(name="Zubair Khan", username="z1")
    make_client_record(name="Aleya Begum", username="a1")
    make_client_record(name="Milon Das", username="m1")

    assert _names(owner_client.get(reverse("client_list"), {"sort": "name"})) == [
        "Aleya Begum",
        "Milon Das",
        "Zubair Khan",
    ]


def test_clicking_the_sorted_column_reverses_it(owner_client, make_client_record):
    make_client_record(name="Aleya Begum", username="a1")
    make_client_record(name="Zubair Khan", username="z1")

    response = owner_client.get(reverse("client_list"), {"sort": "-name"})
    assert _names(response) == ["Zubair Khan", "Aleya Begum"]


def test_clients_sort_by_what_they_owe(owner_client, make_client_record, period):
    from apps.accountants.models import Invoice
    from apps.accountants.services import generate_invoices, record_payment

    make_client_record(name="Settled Up", username="paid1")
    make_client_record(name="In Arrears", username="owes1")
    generate_invoices(period)
    # Clear one of the two bills, so the other is the only debtor.
    record_payment(Invoice.objects.get(client__username="paid1"), Decimal("800.00"))

    assert _names(owner_client.get(reverse("client_list"), {"sort": "-owes"}))[0] == "In Arrears"


def test_an_unknown_sort_key_is_ignored(owner_client, make_client_record):
    """User input never reaches `order_by` — a crafted key would otherwise let
    a reader sort on a related table's columns."""
    make_client_record(name="Someone", username="s1")
    response = owner_client.get(reverse("client_list"), {"sort": "pop__clients__nid"})
    assert response.status_code == 200
    assert response.context["sort"] == "-joined"  # fell back to the default


def test_the_sort_link_keeps_the_active_search(owner_client, make_client_record):
    make_client_record(name="Findable", username="f1")
    body = owner_client.get(reverse("client_list"), {"q": "Find"}).content.decode()
    assert "q=Find" in body
    assert "sort=name" in body


def test_sorting_returns_to_the_first_page(owner_client, make_client_record):
    """Page 7 of the old order is meaningless in the new one."""
    for index in range(30):
        make_client_record(name=f"Client {index}", username=f"p{index}")
    body = owner_client.get(reverse("client_list"), {"page": 2}).content.decode()
    assert "page=2&amp;sort=name" not in body and "sort=name&amp;page=2" not in body


# ---------------------------------------------------------------------------#
# Status chips
# ---------------------------------------------------------------------------#


def test_the_status_chips_carry_the_counts(owner_client, make_client_record):
    make_client_record(username="c1")
    make_client_record(username="c2", status=Client.Status.SUSPENDED)
    make_client_record(username="c3", status=Client.Status.TERMINATED)

    counts = owner_client.get(reverse("client_list")).context["status_counts"]
    assert counts["total"] == 3
    assert counts["active"] == 1
    assert counts["suspended"] == 1
    assert counts["terminated"] == 1


def test_a_chip_filters_the_list(owner_client, make_client_record):
    make_client_record(name="Still Here", username="c1")
    make_client_record(name="Paused", username="c2", status=Client.Status.SUSPENDED)

    response = owner_client.get(reverse("client_list"), {"status": "suspended"})
    assert _names(response) == ["Paused"]
    applied = [chip.label for chip in response.context["chips"] if chip.is_active]
    assert applied == ["Suspended"]


def test_the_applied_chip_is_marked(owner_client, make_client_record):
    make_client_record(username="c1", status=Client.Status.SUSPENDED)
    body = owner_client.get(reverse("client_list"), {"status": "suspended"}).content.decode()
    assert "chip-on" in body


# ---------------------------------------------------------------------------#
# Packages
# ---------------------------------------------------------------------------#


def test_package_totals_count_only_live_subscriptions(owner_client, make_client_record, package):
    make_client_record(username="p1")
    gone = make_client_record(username="p2")
    gone.subscription.cancel()

    totals = owner_client.get(reverse("package_list")).context["totals"]
    assert totals["subscribers"] == 1
    assert totals["revenue"] == Decimal("800.00")


def test_package_revenue_is_net_of_discount(owner_client, make_client_record):
    make_client_record(username="d1", price="800.00", discount="50.00")
    assert owner_client.get(reverse("package_list")).context["totals"]["revenue"] == Decimal(
        "750.00"
    )


def test_package_share_bars_scale_to_the_busiest_plan(owner_client, make_client_record, package):
    make_client_record(username="s1")
    make_client_record(username="s2")
    assert owner_client.get(reverse("package_list")).context["busiest"] == 2


def test_busiest_is_never_zero(owner_client, package):
    """The template divides by it to size the bars."""
    assert owner_client.get(reverse("package_list")).context["busiest"] == 1


def test_packages_sort_by_subscriber_count(owner_client, make_client_record, package, pop):
    quiet = Package.objects.create(
        name="Quiet plan", bandwidth_mbps=5, monthly_price=Decimal("300")
    )
    make_client_record(username="b1")
    busy = Client.objects.create(
        name="Second", username="b2", phone="01712345678", address="x", pop=pop
    )
    Subscription.objects.create(client=busy, package=package, monthly_price=Decimal("800"))

    rows = list(
        owner_client.get(reverse("package_list"), {"sort": "-subscribers"}).context["packages"]
    )
    assert [row.name for row in rows] == [package.name, quiet.name]


# ---------------------------------------------------------------------------#
# POPs
# ---------------------------------------------------------------------------#


def test_pops_list_parents_before_their_children(owner_client):
    main = Pop.objects.create(name="Main POP")
    Pop.objects.create(name="Alpha sub", parent=main)
    Pop.objects.create(name="Beta sub", parent=main)
    Pop.objects.create(name="Zulu standalone")

    rows = owner_client.get(reverse("pop_list")).context["pops"]
    assert [row.name for row in rows] == ["Main POP", "Alpha sub", "Beta sub", "Zulu standalone"]
    assert [row.depth for row in rows] == [0, 1, 1, 0]


def test_a_nested_pop_is_indented_further(owner_client):
    main = Pop.objects.create(name="Main")
    child = Pop.objects.create(name="Child", parent=main)
    Pop.objects.create(name="Grandchild", parent=child)

    depths = {row.name: row.depth for row in owner_client.get(reverse("pop_list")).context["pops"]}
    assert depths == {"Main": 0, "Child": 1, "Grandchild": 2}


def test_pop_totals_count_clients_and_empty_nodes(owner_client, make_client_record, pop):
    Pop.objects.create(name="Unused POP")
    make_client_record(username="c1")

    totals = owner_client.get(reverse("pop_list")).context["totals"]
    assert totals["pops"] == 2
    assert totals["clients"] == 1
    assert totals["unattached"] == 1


def test_pop_list_survives_an_empty_estate(owner_client):
    response = owner_client.get(reverse("pop_list"))
    assert response.status_code == 200
    assert response.context["busiest"] == 1  # never zero: the bars divide by it


# ---------------------------------------------------------------------------#
# Client detail
# ---------------------------------------------------------------------------#


def test_the_client_profile_shows_the_facts_a_support_call_needs(
    owner_client, make_client_record, onu
):
    record = make_client_record(name="Rahim Uddin", username="rahim", onu=onu)
    body = owner_client.get(reverse("client_detail", args=[record.pk])).content.decode()

    assert "Rahim Uddin" in body
    assert record.client_code in body
    assert onu.serial in body
    assert "Collected by" in body


def test_the_profile_states_who_collects_the_bill(owner_client, make_client_record):
    from apps.core.choices import CollectionMode

    record = make_client_record(username="direct", collection_mode=CollectionMode.UPSTREAM)
    body = owner_client.get(reverse("client_detail", args=[record.pk])).content.decode()
    assert "Upstream, directly" in body


# ---------------------------------------------------------------------------#
# The shared index-page components
# ---------------------------------------------------------------------------#

INDEX_PAGES = ["client_list", "package_list", "pop_list"]


@pytest.mark.parametrize("page", INDEX_PAGES)
def test_every_index_page_uses_the_same_skeleton(owner_client, page):
    """Chips, toolbar, table and pagination — the same three pieces each time."""
    body = owner_client.get(reverse(page)).content.decode()
    assert 'class="filter-chips"' in body
    assert 'class="toolbar"' in body
    assert 'class="toolbar-search"' in body
    assert "index-table" in body


@pytest.mark.parametrize("page", INDEX_PAGES)
def test_every_index_page_offers_a_search_box(owner_client, page):
    response = owner_client.get(reverse(page))
    assert "q" in response.context["filter"].form.fields


@pytest.mark.parametrize("page", INDEX_PAGES)
def test_every_index_page_reports_how_many_rows_matched(owner_client, page):
    assert "toolbar-count" in owner_client.get(reverse(page)).content.decode()


@pytest.mark.parametrize(
    "page,param,applied",
    [
        ("client_list", "status", "suspended"),
        ("package_list", "is_active", "false"),
        ("pop_list", "is_active", "false"),
    ],
)
def test_the_leading_chip_clears_the_filter(owner_client, page, param, applied):
    chips = owner_client.get(reverse(page), {param: applied}).context["chips"]

    # The "All ..." chip removes the parameter entirely, and is not the one
    # marked as current while a narrower chip is applied.
    assert param not in chips[0].url
    assert chips[0].is_active is False
    assert [chip.is_active for chip in chips].count(True) == 1


@pytest.mark.parametrize("page", INDEX_PAGES)
def test_a_chip_keeps_the_rest_of_the_query(owner_client, page):
    """Clicking a chip narrows the list; it does not throw away the search."""
    chips = owner_client.get(reverse(page), {"q": "abc"}).context["chips"]
    assert all("q=abc" in chip.url for chip in chips)


def test_a_pill_names_the_filter_in_the_reader_s_words(owner_client, make_client_record):
    """`Status: Active`, not `status: active`."""
    import re

    make_client_record(username="c1")
    body = owner_client.get(reverse("client_list"), {"status": "active"}).content.decode()
    pills = re.findall(r'<span class="pill-key">([^<]+)</span>\s*([^<]+)', body)
    assert [(key.strip(), value.strip()) for key, value in pills] == [("Status", "Active")]


def test_a_pill_resolves_a_foreign_key_to_its_name(owner_client, make_client_record, pop):
    make_client_record(username="c1")
    body = owner_client.get(reverse("client_list"), {"pop": pop.pk}).content.decode()
    assert pop.name in body
    assert f'pill-key">POP</span>{pop.pk}' not in body


def test_removing_one_pill_keeps_the_other_filters(owner_client, make_client_record):
    import re

    make_client_record(name="Rahim Uddin", username="c1")
    body = owner_client.get(
        reverse("client_list"), {"q": "Rahim", "status": "active"}
    ).content.decode()
    removals = re.findall(r'class="pill-remove" href="([^"]+)"', body)

    assert len(removals) == 2
    # Each remove link drops exactly its own key and keeps the other.
    assert any("status=active" in url and "q=Rahim" not in url for url in removals)
    assert any("q=Rahim" in url and "status=active" not in url for url in removals)


def test_no_pills_are_shown_when_nothing_is_filtered(owner_client):
    assert "active-filters" not in owner_client.get(reverse("client_list")).content.decode()


# ---------------------------------------------------------------------------#
# Package and POP filters
# ---------------------------------------------------------------------------#


def test_packages_filter_by_availability(owner_client, package):
    Package.objects.create(
        name="Old plan", bandwidth_mbps=8, monthly_price=Decimal("400"), is_active=False
    )
    on_sale = owner_client.get(reverse("package_list"), {"is_active": "true"})
    retired = owner_client.get(reverse("package_list"), {"is_active": "false"})

    assert [row.name for row in on_sale.context["packages"]] == [package.name]
    assert [row.name for row in retired.context["packages"]] == ["Old plan"]


def test_packages_filter_by_speed_band(owner_client, package):
    Package.objects.create(name="Fast", bandwidth_mbps=100, monthly_price=Decimal("3500"))
    rows = owner_client.get(reverse("package_list"), {"speed": "51-"}).context["packages"]
    assert [row.name for row in rows] == ["Fast"]


def test_packages_search_covers_the_description(owner_client):
    Package.objects.create(
        name="Plan A",
        bandwidth_mbps=10,
        monthly_price=Decimal("500"),
        description="Unlimited fibre",
    )
    rows = owner_client.get(reverse("package_list"), {"q": "fibre"}).context["packages"]
    assert [row.name for row in rows] == ["Plan A"]


def test_pops_can_be_searched(owner_client):
    Pop.objects.create(name="Station Road Node", code="N001", address="12 Station Road")
    Pop.objects.create(name="College Para Node", code="N002", address="9 College Para")

    rows = owner_client.get(reverse("pop_list"), {"q": "station"}).context["pops"]
    assert [row.name for row in rows] == ["Station Road Node"]


def test_pops_filter_by_upstream(owner_client):
    core = Pop.objects.create(name="Core")
    Pop.objects.create(name="Child A", parent=core)
    Pop.objects.create(name="Elsewhere")

    rows = owner_client.get(reverse("pop_list"), {"parent": core.pk}).context["pops"]
    assert [row.name for row in rows] == ["Child A"]


def test_pops_filter_by_status(owner_client):
    Pop.objects.create(name="Live node")
    Pop.objects.create(name="Dead node", is_active=False)

    rows = owner_client.get(reverse("pop_list"), {"is_active": "false"}).context["pops"]
    assert [row.name for row in rows] == ["Dead node"]


def test_the_pop_tree_is_built_before_pagination(owner_client):
    """A child on page 2 must not end up under a parent left on page 1.

    The tree is ordered across the whole result and then paginated, so the
    depths stay consistent however the pages fall.
    """
    core = Pop.objects.create(name="Core")
    for index in range(60):
        Pop.objects.create(name=f"Node {index:03d}", parent=core)

    first = owner_client.get(reverse("pop_list")).context["pops"]
    second = owner_client.get(reverse("pop_list"), {"page": 2}).context["pops"]

    assert first[0].name == "Core" and first[0].depth == 0
    assert all(row.depth == 1 for row in first[1:])
    assert all(row.depth == 1 for row in second)
    assert len(first) + len(second) == 61


def test_a_pop_whose_parent_is_filtered_out_still_appears(owner_client):
    core = Pop.objects.create(name="Core")
    Pop.objects.create(name="Orphan node", parent=core)

    rows = owner_client.get(reverse("pop_list"), {"q": "Orphan"}).context["pops"]
    assert [row.name for row in rows] == ["Orphan node"]
    assert rows[0].depth == 0  # shown at the root rather than dropped


def test_the_seed_builds_a_real_estate_at_the_documented_size(db):
    """The demo has to exercise pagination and the POP tree, not just render."""
    from io import StringIO

    from django.core.management import call_command

    from apps.accountants.models import Payment
    from apps.core.choices import CollectionMode

    call_command("seed_demo", clients=40, pops=25, months=2, stdout=StringIO())

    assert Client.objects.count() == 40
    assert Package.objects.count() == 15
    assert Pop.objects.count() == 25
    assert Payment.objects.exists()

    # A three-level tree, both settlement arrangements, and retired plans that
    # clients are still on — the states the pages are built to show.
    assert Pop.objects.filter(parent__isnull=True).count() == 1
    assert Pop.objects.filter(parent__parent__isnull=False).exists()
    assert Pop.objects.filter(is_active=False).exists()
    assert Package.objects.filter(is_active=False).count() == 2
    assert Client.objects.filter(collection_mode=CollectionMode.UPSTREAM).exists()
    assert Client.objects.filter(collection_mode=CollectionMode.RESELLER).exists()


def test_the_seed_refuses_to_run_over_existing_clients(db, client_record):
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    with pytest.raises(CommandError, match="already has clients"):
        call_command("seed_demo", stdout=StringIO())
