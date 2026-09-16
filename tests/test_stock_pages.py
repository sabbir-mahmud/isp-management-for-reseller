"""Stock, categories and movements: levels, values, prefills and the stock guards."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.users.models import Role
from apps.users.roles import sync_roles
from apps.warehouse.models import Category, Product, StockMovement


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("shelfboss", Role.OWNER))
    return client


def _stock(product, quantity):
    StockMovement.objects.create(product=product, kind=StockMovement.Kind.IN, quantity=quantity)
    product.refresh_from_db()
    return product


@pytest.fixture
def shelf(db):
    """Healthy patch cords, low drop wire, no connectors, and an empty category."""
    networking = Category.objects.create(name="Networking")
    Category.objects.create(name="Tools")
    cords = _stock(
        Product.objects.create(
            name="Patch cord", category=networking, unit_price="80", reorder_level=10
        ),
        50,
    )
    wire = _stock(
        Product.objects.create(
            name="Drop wire", category=networking, unit_price="1200", reorder_level=10
        ),
        4,
    )
    connectors = Product.objects.create(
        name="SC connector", category=networking, unit_price="15", reorder_level=20
    )
    return {"cords": cords, "wire": wire, "connectors": connectors, "networking": networking}


def _names(response, key="products"):
    return [obj.name for obj in response.context[key]]


# ---- Stock ------------------------------------------------------------------


def test_stock_levels_split_the_shelf(owner_client, shelf):
    response = owner_client.get(reverse("product_list"))
    totals = response.context["totals"]

    assert (totals["healthy"], totals["low"], totals["out"]) == (1, 1, 1)
    assert totals["units"] == 54
    assert totals["value"] == Decimal("8800.00")  # 50 × 80 + 4 × 1200
    assert [item["name"] for item in response.context["reorder"]] == ["SC connector", "Drop wire"]
    assert b"to reorder" in response.content


@pytest.mark.parametrize(
    "level,expected",
    [("healthy", ["Patch cord"]), ("low", ["Drop wire"]), ("out", ["SC connector"])],
)
def test_the_level_filter(owner_client, shelf, level, expected):
    assert _names(owner_client.get(reverse("product_list"), {"level": level})) == expected


def test_stock_sorts_by_value(owner_client, shelf):
    response = owner_client.get(reverse("product_list"), {"sort": "-value"})
    assert _names(response) == ["Drop wire", "Patch cord", "SC connector"]


def test_rows_offer_receive_and_only_issue_what_is_there(owner_client, shelf):
    body = owner_client.get(reverse("product_list")).content.decode()
    receive = f"?product={shelf['connectors'].pk}&kind=in&next=stock"
    issue = f"?product={shelf['connectors'].pk}&kind=out"
    assert receive in body
    assert issue not in body  # nothing to issue


def test_a_new_item_can_start_in_a_category(owner_client, shelf):
    pk = shelf["networking"].pk
    response = owner_client.get(reverse("product_add"), {"category": pk})
    assert response.context["form"].initial["category"] == str(pk)


# ---- Categories -------------------------------------------------------------


def test_categories_show_what_they_hold(owner_client, shelf):
    response = owner_client.get(reverse("category_list"))
    rows = {category.name: category for category in response.context["categories"]}

    assert response.context["totals"]["count"] == 2
    assert response.context["totals"]["empty"] == 1
    assert rows["Networking"].products_count == 3
    assert rows["Networking"].units == 54
    assert rows["Networking"].value == Decimal("8800.00")
    assert rows["Networking"].attention == 2
    assert rows["Networking"].share == 100
    assert rows["Tools"].products_count == 0


def test_only_empty_categories_offer_delete(owner_client, shelf):
    body = owner_client.get(reverse("category_list")).content.decode()
    assert reverse("category_delete", args=[shelf["networking"].pk]) not in body
    tools = Category.objects.get(name="Tools")
    assert reverse("category_delete", args=[tools.pk]) in body


def test_categories_sort_by_value(owner_client, shelf):
    response = owner_client.get(reverse("category_list"), {"sort": "-value"})
    assert _names(response, "categories") == ["Networking", "Tools"]


# ---- Movements --------------------------------------------------------------


def test_movement_totals_follow_the_search(owner_client, shelf):
    StockMovement.objects.create(product=shelf["cords"], kind="out", quantity=5)
    StockMovement.objects.create(product=shelf["cords"], kind="adjust", quantity=-2)

    totals = owner_client.get(reverse("movement_list")).context["totals"]
    assert (totals["received"], totals["issued"], totals["adjusted"]) == (54, 5, -2)
    assert totals["net"] == 47

    response = owner_client.get(reverse("movement_list"), {"q": "patch"})
    assert response.context["totals"]["net"] == 43
    assert "−2" in response.content.decode()


def test_the_movement_chips_count_each_type(owner_client, shelf):
    chips = {
        chip.label: chip.value
        for chip in owner_client.get(reverse("movement_list")).context["chips"]
    }
    assert chips == {"All movements": 2, "Received": 2, "Issued": 0, "Adjustments": 0}


def test_the_movement_form_is_prefilled_and_returns_to_stock(owner_client, shelf):
    wire = shelf["wire"]
    url = f"{reverse('movement_add')}?product={wire.pk}&kind=in&next=stock"
    response = owner_client.get(url)
    assert response.context["form"].initial["product"] == wire.pk
    assert response.context["form"].initial["kind"] == "in"
    assert response.context["stock_levels"][str(wire.pk)] == {"quantity": 4, "reorder": 10}

    response = owner_client.post(
        url,
        {"product": wire.pk, "kind": "in", "quantity": 6, "occurred_on": "2026-09-16"},
    )
    assert response.status_code == 302
    assert response.url == reverse("product_list")
    wire.refresh_from_db()
    assert wire.quantity == 10


def test_an_adjustment_cannot_take_stock_below_zero(owner_client, shelf):
    wire = shelf["wire"]
    response = owner_client.post(
        reverse("movement_add"),
        {"product": wire.pk, "kind": "adjust", "quantity": -5, "occurred_on": "2026-09-16"},
    )
    assert response.status_code == 200
    assert "below zero" in str(response.context["form"].errors["quantity"])
    wire.refresh_from_db()
    assert wire.quantity == 4


def test_a_zero_adjustment_is_refused(owner_client, shelf):
    response = owner_client.post(
        reverse("movement_add"),
        {"product": shelf["wire"].pk, "kind": "adjust", "quantity": 0, "occurred_on": "2026-09-16"},
    )
    assert "changes nothing" in str(response.context["form"].errors["quantity"])


def test_retired_items_are_not_offered_for_movements(owner_client, shelf):
    Product.objects.filter(pk=shelf["connectors"].pk).update(status=Product.Status.RETIRED)
    choices = owner_client.get(reverse("movement_add")).context["form"].fields["product"].queryset
    assert shelf["connectors"] not in choices


def test_absolute_drops_the_sign():
    from apps.core.templatetags.ui import absolute

    assert absolute(-3) == 3
    assert absolute(Decimal("-1.50")) == Decimal("1.50")
    assert absolute("x") == "x"


# ---- Category form ----------------------------------------------------------


def test_a_category_name_differing_only_in_case_is_refused(owner_client, shelf):
    response = owner_client.post(
        reverse("category_add"), {"name": "  networking ", "description": ""}
    )
    assert response.status_code == 200
    assert "Networking already exists" in str(response.context["form"].errors["name"])
    assert Category.objects.count() == 2


def test_a_category_can_keep_its_own_name_when_edited(owner_client, shelf):
    networking = shelf["networking"]
    response = owner_client.post(
        reverse("category_edit", args=[networking.pk]),
        {"name": "NETWORKING", "description": "Cables and connectors"},
    )
    assert response.status_code == 302
    networking.refresh_from_db()
    assert networking.name == "NETWORKING"


def test_the_name_is_tidied_before_saving(owner_client, shelf):
    owner_client.post(reverse("category_add"), {"name": "  Power   supplies ", "description": ""})
    assert Category.objects.filter(name="Power supplies").exists()


def test_create_and_add_an_item_goes_to_the_new_item_form(owner_client, shelf):
    response = owner_client.post(
        reverse("category_add"), {"name": "Power", "description": "", "then": "add_item"}
    )
    power = Category.objects.get(name="Power")
    assert response.url == f"{reverse('product_add')}?category={power.pk}"


def test_the_category_form_lists_other_names_for_the_duplicate_hint(owner_client, shelf):
    networking = shelf["networking"]
    response = owner_client.get(reverse("category_edit", args=[networking.pk]))
    body = response.content.decode()

    assert response.context["form"].other_names == ["Tools"]  # not itself
    assert 'data-existing="Tools"' in body
    assert 'id="category-names"' in body
    assert "Create and add an item" not in body  # only offered when creating


def test_editing_a_category_shows_what_it_holds(owner_client, shelf):
    holdings = owner_client.get(reverse("category_edit", args=[shelf["networking"].pk])).context[
        "holdings"
    ]
    assert holdings["items"] == 3
    assert holdings["units"] == 54
    assert holdings["value"] == Decimal("8800.00")
    assert holdings["to_reorder"] == 2
    assert holdings["sample"] == ["Drop wire", "Patch cord", "SC connector"]
    assert holdings["more"] == 0


def test_the_add_category_form_offers_create_and_add(owner_client, shelf):
    body = owner_client.get(reverse("category_add")).content.decode()
    assert "Create and add an item" in body
    assert "is-sectioned" in body
    assert "On the categories list" in body
