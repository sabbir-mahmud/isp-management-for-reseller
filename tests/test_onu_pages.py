"""The ONU list and form: fleet summary, model mix, sorting and the status guard."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.users.models import Role
from apps.users.roles import sync_roles
from apps.warehouse.models import Onu


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("stockboss", Role.OWNER))
    return client


@pytest.fixture
def fleet(db, make_client_record):
    """Two VSOLs (one installed, one spare) and a faulty Huawei."""
    installed = Onu.objects.create(
        serial="VSOL-1", model="VSOL V2802", purchase_price="1500", status=Onu.Status.ASSIGNED
    )
    make_client_record(name="Rahim Uddin", username="rahim", onu=installed)
    Onu.objects.create(serial="VSOL-2", model="VSOL V2802", purchase_price="1500")
    Onu.objects.create(
        serial="HW-1",
        model="Huawei HG8310",
        purchase_price="2000",
        status=Onu.Status.FAULTY,
        note="Dead PON port",
    )
    return installed


def test_the_fleet_summary_counts_and_values_every_unit(owner_client, fleet):
    response = owner_client.get(reverse("onu_list"), {"status": "faulty"})
    summary = response.context["fleet"]

    # The summary ignores the search; the table does not.
    assert summary["total"] == 3
    assert summary["value"] == Decimal("5000.00")
    assert summary["in_stock_count"] == 1
    assert summary["in_stock_value"] == Decimal("1500.00")
    assert summary["out_of_service"] == 1
    assert summary["deployed_percent"] == 33
    assert [onu.serial for onu in response.context["onus"]] == ["HW-1"]


def test_the_model_breakdown_splits_each_model(owner_client, fleet):
    rows = {row["model"]: row for row in owner_client.get(reverse("onu_list")).context["models"]}

    assert rows["VSOL V2802"]["total"] == 2
    assert rows["VSOL V2802"]["assigned"] == 1
    assert rows["VSOL V2802"]["in_stock"] == 1
    assert rows["Huawei HG8310"]["out"] == 1
    assert "model=VSOL" in rows["VSOL V2802"]["url"]


def test_onus_can_be_found_by_the_client_they_are_with(owner_client, fleet):
    response = owner_client.get(reverse("onu_list"), {"q": "rahim"})
    assert [onu.serial for onu in response.context["onus"]] == ["VSOL-1"]


def test_onus_filter_by_model_and_sort_by_cost(owner_client, fleet):
    response = owner_client.get(reverse("onu_list"), {"model": "VSOL V2802", "sort": "-cost"})
    assert {onu.serial for onu in response.context["onus"]} == {"VSOL-1", "VSOL-2"}

    response = owner_client.get(reverse("onu_list"), {"sort": "-cost"})
    assert response.context["onus"][0].serial == "HW-1"


def test_an_empty_shelf_is_called_out(owner_client, fleet):
    Onu.objects.filter(serial="VSOL-2").update(status=Onu.Status.RETIRED)
    assert b"No spare ONUs" in owner_client.get(reverse("onu_list")).content


def test_an_installed_onu_cannot_be_deleted_from_the_list(owner_client, fleet):
    body = owner_client.get(reverse("onu_list")).content.decode()
    assert reverse("onu_delete", args=[fleet.pk]) not in body


def test_an_installed_onus_status_cannot_be_changed_here(owner_client, fleet):
    response = owner_client.post(
        reverse("onu_edit", args=[fleet.pk]),
        {
            "serial": "VSOL-1",
            "model": "VSOL V2802",
            "port": 1,
            "purchase_price": "1500",
            "purchased_on": "2026-01-01",
            "status": "in_stock",  # ignored: the field is disabled
            "note": "",
            "name": "",
        },
    )
    assert response.status_code == 302
    fleet.refresh_from_db()
    assert fleet.status == Onu.Status.ASSIGNED


def test_a_spare_onu_cannot_be_marked_assigned_here(owner_client, fleet):
    spare = Onu.objects.get(serial="VSOL-2")
    response = owner_client.post(
        reverse("onu_edit", args=[spare.pk]),
        {
            "serial": "VSOL-2",
            "model": "VSOL V2802",
            "port": 1,
            "purchase_price": "1500",
            "purchased_on": "2026-01-01",
            "status": "assigned",
            "note": "",
            "name": "",
        },
    )
    assert response.status_code == 200
    assert "status" in response.context["form"].errors
    spare.refresh_from_db()
    assert spare.status == Onu.Status.IN_STOCK


def test_the_onu_form_suggests_existing_models(owner_client, fleet):
    body = owner_client.get(reverse("onu_add")).content.decode()
    assert 'list="onu-models"' in body
    assert '<option value="Huawei HG8310">' in body
    assert "is-sectioned" in body
    assert body.count('class="choice-tile"') == 3  # no "Assigned" tile


def test_age_reads_in_the_units_that_matter():
    import datetime as dt

    from apps.core.templatetags.ui import age

    today = dt.date(2026, 9, 16)
    assert age(today, today) == "today"
    assert age(dt.date(2026, 9, 4), today) == "12 days"
    assert age(dt.date(2026, 3, 17), today) == "5 months"
    assert age(dt.date(2024, 6, 1), today) == "2 years 3 months"
    assert age(None) == ""
