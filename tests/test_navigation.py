"""Sidebar behaviour: active state, badges and icons.

The visual design is not testable here, but the logic behind it is — and the
active-state rule in particular is easy to break, because several URL names
share a prefix ("billing_settings" and "settlement_list" both start "s...").
"""

import pytest
from django.core.cache import cache
from django.urls import reverse

from apps.core.templatetags.icons import icon
from apps.users.models import Role
from apps.users.roles import sync_roles


@pytest.fixture(autouse=True)
def _roles(db):
    sync_roles()


@pytest.fixture(autouse=True)
def _clear_badge_cache():
    """Badge counts are cached for a minute, so they leak between tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def owner_client(client, make_user):
    client.force_login(make_user("navboss", Role.OWNER))
    return client


def _active_links(response) -> list[str]:
    import re

    return re.findall(r'class="nav-link active" href="([^"]+)"', response.content.decode())


@pytest.mark.parametrize(
    "page,expected",
    [
        ("dashboard", "/"),
        ("client_list", "/clients/"),
        ("package_list", "/packages/"),
        ("invoice_list", "/billing/invoices/"),
        ("payment_list", "/billing/payments/"),
        ("settlement_list", "/billing/upstream/"),
        ("income_list", "/billing/income/"),
        ("expense_list", "/billing/expenses/"),
        ("billing_settings", "/billing/settings/"),
        ("financial_report", "/reports/financial/"),
        ("onu_list", "/inventory/onus/"),
        ("product_list", "/inventory/stock/"),
        ("category_list", "/inventory/categories/"),
        ("movement_list", "/inventory/movements/"),
        ("staff_list", "/staff/"),
    ],
)
def test_exactly_one_nav_item_is_active_per_page(owner_client, page, expected):
    response = owner_client.get(reverse(page))
    assert _active_links(response) == [expected]


def test_a_detail_page_keeps_its_section_highlighted(owner_client, client_record):
    """Opening a client should not drop the Clients link out of the active state."""
    response = owner_client.get(reverse("client_detail", args=[client_record.pk]))
    assert _active_links(response) == ["/clients/"]


def test_a_sub_page_keeps_its_section_highlighted(owner_client):
    response = owner_client.get(reverse("settlement_add"))
    assert _active_links(response) == ["/billing/upstream/"]


def test_settings_and_settlement_do_not_highlight_each_other(owner_client):
    """Their URL names overlap, which a naive prefix match gets wrong."""
    assert _active_links(owner_client.get(reverse("billing_settings"))) == ["/billing/settings/"]
    assert _active_links(owner_client.get(reverse("settlement_list"))) == ["/billing/upstream/"]


def test_the_sidebar_only_shows_sections_the_role_can_reach(client, make_user):
    client.force_login(make_user("navsupport", Role.SUPPORT))
    body = client.get(reverse("client_list")).content.decode()

    assert 'href="/clients/"' in body
    assert 'href="/billing/invoices/"' in body
    # Support has no dashboard, settlement, ledger or staff access.
    assert 'href="/billing/upstream/"' not in body
    assert 'href="/billing/expenses/"' not in body
    assert 'href="/staff/"' not in body
    assert 'data-nav-group="admin"' not in body


def test_overdue_invoices_show_as_a_badge(owner_client, client_record, period):
    from datetime import timedelta

    from apps.accountants.models import Invoice
    from apps.accountants.services import generate_invoices, refresh_overdue

    generate_invoices(period)
    invoice = Invoice.objects.get()
    Invoice.objects.filter(pk=invoice.pk).update(
        due_date=invoice.issue_date - timedelta(days=5), status=Invoice.Status.UNPAID
    )
    refresh_overdue()

    body = owner_client.get(reverse("dashboard")).content.decode()
    assert 'class="nav-badge nav-badge-danger">1<' in body


def test_badges_are_skipped_for_a_role_without_the_permission(client, make_user, django_user_model):
    """No badge means no query: the count is only fetched for someone who can act on it."""
    user = make_user("nobadge", Role.SUPPORT)
    user.user_permissions.clear()
    user.groups.clear()
    client.force_login(django_user_model.objects.get(pk=user.pk))

    response = client.get(reverse("healthz"))
    assert response.status_code == 200

    # A user with the permission does get the counts.
    client.force_login(make_user("withbadge", Role.OWNER))
    context = client.get(reverse("dashboard")).context["nav_badges"]
    assert "overdue_invoices" in context
    assert "low_stock" in context


def test_every_nav_item_renders_an_icon(owner_client):
    body = owner_client.get(reverse("dashboard")).content.decode()
    nav_links = body.count('class="nav-link')
    icons = body.count('<svg class="icon"')
    # Every link carries one icon, plus the two footer buttons and the close button.
    assert icons >= nav_links


def test_an_unknown_icon_renders_nothing_rather_than_raising():
    assert icon("no-such-icon") == ""


def test_a_known_icon_renders_inline_svg():
    markup = icon("clients")
    assert markup.startswith("<svg")
    assert 'stroke="currentColor"' in markup


def test_the_mobile_drawer_has_a_control(owner_client):
    """The drawer was previously styled but unopenable on small screens."""
    body = owner_client.get(reverse("dashboard")).content.decode()
    assert "data-sidebar-toggle" in body
    assert "sidebar-backdrop" in body


# ---------------------------------------------------------------------------#
# Nested groups
# ---------------------------------------------------------------------------#


def _open_groups(response) -> list[str]:
    import re

    body = response.content.decode()
    return [
        match.group(2)
        for match in re.finditer(r'<div class="nav-group( open)?" data-nav-group="([^"]+)"', body)
        if match.group(1)
    ]


def _all_groups(response) -> list[str]:
    import re

    return re.findall(r'data-nav-group="([^"]+)"', response.content.decode())


@pytest.mark.parametrize(
    "page,expected_group",
    [
        ("client_list", "customers"),
        ("package_list", "customers"),
        ("pop_list", "customers"),
        ("invoice_list", "billing"),
        ("payment_list", "billing"),
        ("settlement_list", "billing"),
        ("expense_list", "billing"),
        ("income_list", "billing"),
        ("onu_list", "inventory"),
        ("product_list", "inventory"),
        ("category_list", "inventory"),
        ("movement_list", "inventory"),
        ("staff_list", "admin"),
        ("billing_settings", "admin"),
    ],
)
def test_the_group_holding_the_open_page_is_expanded(owner_client, page, expected_group):
    """Server-rendered, so the sidebar never paints shut and then jumps open."""
    response = owner_client.get(reverse(page))
    assert _open_groups(response) == [expected_group]


def test_a_sub_page_expands_its_parent_group(owner_client, client_record):
    assert _open_groups(owner_client.get(reverse("settlement_add"))) == ["billing"]
    assert _open_groups(owner_client.get(reverse("client_detail", args=[client_record.pk]))) == [
        "customers"
    ]


@pytest.mark.parametrize("page", ["dashboard", "financial_report"])
def test_top_level_pages_expand_nothing(owner_client, page):
    """Dashboard and the report are standalone links; a group of one is noise."""
    assert _open_groups(owner_client.get(reverse(page))) == []


def test_every_group_reports_its_state_to_assistive_tech(owner_client):
    import re

    body = owner_client.get(reverse("invoice_list")).content.decode()
    states = {
        slug: value == "true"
        for value, slug in re.findall(
            r'aria-expanded="(\w+)" aria-controls="nav-group-([^"]+)"', body
        )
    }
    assert states == {"customers": False, "billing": True, "inventory": False, "admin": False}


def test_groups_with_no_permitted_children_are_not_rendered(client, make_user):
    client.force_login(make_user("navgroups", Role.SUPPORT))
    response = client.get(reverse("client_list"))
    assert _all_groups(response) == ["customers", "billing", "inventory"]


def test_a_closed_group_still_surfaces_its_count(owner_client, client_record, period):
    """An overdue bill must not be hidden just because Billing is collapsed."""
    from datetime import timedelta

    from apps.accountants.models import Invoice
    from apps.accountants.services import generate_invoices, refresh_overdue

    generate_invoices(period)
    invoice = Invoice.objects.get()
    Invoice.objects.filter(pk=invoice.pk).update(
        due_date=invoice.issue_date - timedelta(days=5), status=Invoice.Status.UNPAID
    )
    refresh_overdue()

    body = owner_client.get(reverse("dashboard")).content.decode()
    assert "group-badge" in body


def test_nav_group_rejects_positional_arguments():
    """The tag is keyword-only, so a typo fails loudly at parse time."""
    from django.template import Template, TemplateSyntaxError

    with pytest.raises(TemplateSyntaxError):
        Template('{% load nav %}{% nav_group "Billing" %}{% endnav_group %}')
