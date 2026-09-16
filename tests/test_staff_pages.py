"""Staff list and forms: who is listed, the role guide, and the lockout guards."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.users.models import Profile, Role
from apps.users.roles import sync_roles

User = get_user_model()


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture
def boss(make_user):
    return make_user("boss", Role.OWNER, first_name="Nadia", last_name="Khan")


@pytest.fixture
def owner_client(client, boss):
    client.force_login(boss)
    return client


@pytest.fixture
def team(make_user):
    return {
        "manager": make_user("mgr", Role.MANAGER, first_name="Karim"),
        "support": make_user("sup", Role.SUPPORT, first_name="Rina", is_active=False),
    }


def _update_payload(user, **overrides):
    data = {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": "",
        "role": Profile.objects.get(user=user).role,
        "is_active": "on" if user.is_active else "",
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value != ""}


# ---- List ---------------------------------------------------------------------


def test_a_superuser_without_a_profile_is_listed(owner_client, team):
    legacy = User.objects.create_superuser("legacy", password="x" * 12)
    Profile.objects.filter(user=legacy).delete()

    response = owner_client.get(reverse("staff_list"))
    usernames = [person.username for person in response.context["people"]]
    assert "legacy" in usernames
    assert usernames[:2] == ["boss", "legacy"]  # owners first, the superuser counted as one
    assert b"No profile yet" in response.content


def test_the_staff_summary_and_role_cards(owner_client, team):
    context = owner_client.get(reverse("staff_list")).context
    totals = context["totals"]
    assert (totals["active"], totals["disabled"], totals["owners"]) == (2, 1, 1)

    cards = {card["value"]: card for card in context["roles"]}
    assert cards[Role.MANAGER]["count"] == 1
    assert cards[Role.SUPPORT]["count"] == 0  # the only support account is disabled
    assert "role=manager" in cards[Role.MANAGER]["url"]


def test_a_lone_owner_is_warned_about(owner_client, team):
    assert b"Only one owner can sign in" in owner_client.get(reverse("staff_list")).content


def test_staff_filter_by_role_access_and_search(owner_client, team):
    people = lambda **params: [  # noqa: E731
        p.username for p in owner_client.get(reverse("staff_list"), params).context["people"]
    ]
    assert people(role="manager") == ["mgr"]
    assert people(access="disabled") == ["sup"]
    assert people(q="rina") == ["sup"]


def test_staff_sort_by_last_sign_in_puts_never_last(owner_client, team, boss):
    from django.utils import timezone

    User.objects.filter(pk=boss.pk).update(last_login=timezone.now())
    people = owner_client.get(reverse("staff_list"), {"sort": "-seen"}).context["people"]
    assert people[0].username == "boss"


# ---- Forms --------------------------------------------------------------------


def test_creating_staff_sets_role_and_phone(owner_client):
    response = owner_client.post(
        reverse("staff_add"),
        {
            "username": "karim",
            "password1": "a-long-Passw0rd",
            "password2": "a-long-Passw0rd",
            "first_name": "Karim",
            "role": Role.ACCOUNTANT,
            "phone": "01712345678",
        },
    )
    assert response.status_code == 302
    profile = Profile.objects.get(user__username="karim")
    assert (profile.role, profile.phone) == (Role.ACCOUNTANT, "01712345678")
    assert profile.user.groups.filter(name="role:accountant").exists()


def test_the_staff_form_is_sectioned_with_a_role_guide(owner_client):
    body = owner_client.get(reverse("staff_add")).content.decode()
    assert "is-sectioned" in body
    assert body.count('class="choice-tile"') == 4
    assert 'data-role-guide="owner"' in body
    assert 'class="form-control"' in body  # the inputs are styled now


def test_you_cannot_change_your_own_role_or_access(owner_client, boss):
    response = owner_client.post(
        reverse("staff_edit", args=[boss.pk]),
        _update_payload(boss, role=Role.SUPPORT, is_active=""),
    )
    assert response.status_code == 302
    boss.refresh_from_db()
    assert boss.is_active
    assert boss.profile.role == Role.OWNER


def test_an_owner_can_demote_another_owner(client, make_user, boss):
    """Through the page the acting owner is always another owner, so this is allowed."""
    client.force_login(make_user("helper", Role.OWNER))
    response = client.post(
        reverse("staff_edit", args=[boss.pk]), _update_payload(boss, role=Role.MANAGER)
    )
    assert response.status_code == 302
    assert Profile.objects.get(user=boss).role == Role.MANAGER


def test_the_guard_refuses_leaving_no_owner(make_user, boss):
    """The form refuses to leave nobody able to manage staff, whoever calls it."""
    from apps.users.forms import StaffUpdateForm

    form = StaffUpdateForm(data=_update_payload(boss, role=Role.MANAGER), instance=boss)
    assert not form.is_valid()
    assert "only owner" in str(form.non_field_errors())

    form = StaffUpdateForm(data=_update_payload(boss, is_active=""), instance=boss)
    assert not form.is_valid()

    make_user("second", Role.OWNER)
    form = StaffUpdateForm(data=_update_payload(boss, role=Role.MANAGER), instance=boss)
    assert form.is_valid(), form.errors


def test_editing_a_legacy_superuser_creates_its_profile(owner_client):
    legacy = User.objects.create_superuser("legacy", password="x" * 12)
    Profile.objects.filter(user=legacy).delete()

    page = owner_client.get(reverse("staff_edit", args=[legacy.pk]))
    assert page.status_code == 200
    assert "no staff profile yet" in page.context["notice"]
    assert page.context["form"].fields["role"].initial == Role.OWNER

    response = owner_client.post(
        reverse("staff_edit", args=[legacy.pk]),
        {"first_name": "Old", "role": Role.OWNER, "is_active": "on"},
    )
    assert response.status_code == 302
    assert Profile.objects.get(user=legacy).role == Role.OWNER
