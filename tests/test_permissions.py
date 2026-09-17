"""Access control: what each role can reach.

These tests are the reason roles exist. They assert the negative cases too —
a support technician must not be able to open the books.
"""

import pytest
from django.urls import reverse

from apps.users.models import Role
from apps.users.roles import sync_roles


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


def _login(client, make_user, role, username):
    user = make_user(username, role)
    client.force_login(user)
    return user


ALL_ROLES = [Role.OWNER, Role.MANAGER, Role.ACCOUNTANT, Role.SUPPORT]


@pytest.mark.parametrize("role", ALL_ROLES)
def test_anonymous_users_are_sent_to_login(client, role):
    response = client.get(reverse("client_list"))
    assert response.status_code == 302
    assert reverse("login") in response["Location"]


@pytest.mark.parametrize("role", ALL_ROLES)
def test_every_role_can_list_clients(client, make_user, role):
    _login(client, make_user, role, f"u_{role}")
    assert client.get(reverse("client_list")).status_code == 200


@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.MANAGER, 200),
        (Role.ACCOUNTANT, 200),
        (Role.SUPPORT, 403),
    ],
)
def test_dashboard_access_follows_the_role(client, make_user, role, expected):
    _login(client, make_user, role, f"d_{role}")
    assert client.get(reverse("dashboard")).status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [(Role.OWNER, 200), (Role.MANAGER, 200), (Role.ACCOUNTANT, 403), (Role.SUPPORT, 403)],
)
def test_only_owners_and_managers_can_add_clients(client, make_user, role, expected):
    _login(client, make_user, role, f"a_{role}")
    assert client.get(reverse("client_add")).status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [(Role.OWNER, 200), (Role.MANAGER, 403), (Role.ACCOUNTANT, 403), (Role.SUPPORT, 403)],
)
def test_only_the_owner_manages_staff(client, make_user, role, expected):
    _login(client, make_user, role, f"s_{role}")
    assert client.get(reverse("staff_list")).status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [(Role.OWNER, 200), (Role.MANAGER, 403), (Role.ACCOUNTANT, 403), (Role.SUPPORT, 403)],
)
def test_deleting_an_expense_is_owner_only(client, make_user, role, expected, owner):
    from decimal import Decimal

    from apps.accountants.models import Expense

    expense = Expense.objects.create(description="Bandwidth", amount=Decimal("100.00"))
    _login(client, make_user, role, f"e_{role}")
    assert client.get(reverse("expense_delete", args=[expense.pk])).status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [(Role.OWNER, 200), (Role.MANAGER, 200), (Role.ACCOUNTANT, 200), (Role.SUPPORT, 403)],
)
def test_exports_need_the_export_permission(client, make_user, role, expected):
    _login(client, make_user, role, f"x_{role}")
    response = client.get(reverse("export", args=["clients"]))
    assert response.status_code == expected


def test_support_cannot_reach_the_billing_settings(client, make_user):
    _login(client, make_user, Role.SUPPORT, "support_settings")
    assert client.get(reverse("billing_settings")).status_code == 403


def test_role_change_moves_the_user_between_groups(make_user):
    user = make_user("mover", Role.SUPPORT)
    assert user.has_perm("accounts.view_client")
    assert not user.has_perm("accounts.add_client")

    profile = user.profile
    profile.role = Role.MANAGER
    profile.save()

    user = type(user).objects.get(pk=user.pk)  # drop the cached permissions
    assert user.has_perm("accounts.add_client")


def test_a_user_belongs_to_exactly_one_role_group(make_user):
    user = make_user("single", Role.SUPPORT)
    profile = user.profile
    profile.role = Role.ACCOUNTANT
    profile.save()
    assert user.groups.filter(name__startswith="role:").count() == 1


@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.MANAGER, 200),
        (Role.ACCOUNTANT, 200),
        (Role.SUPPORT, 403),
    ],
)
def test_upstream_settlement_page_follows_the_role(client, make_user, role, expected):
    _login(client, make_user, role, f"set_{role}")
    assert client.get(reverse("settlement_list")).status_code == expected


@pytest.mark.parametrize(
    "role,expected",
    [(Role.OWNER, 200), (Role.MANAGER, 403), (Role.ACCOUNTANT, 403), (Role.SUPPORT, 403)],
)
def test_deleting_a_settlement_is_owner_only(client, make_user, role, expected):
    from decimal import Decimal

    from apps.accountants.models import UpstreamSettlement
    from apps.accountants.services import record_settlement

    settlement = record_settlement(UpstreamSettlement.Kind.REMITTANCE, Decimal("100.00"))
    _login(client, make_user, role, f"setdel_{role}")
    assert client.get(reverse("settlement_delete", args=[settlement.pk])).status_code == expected
