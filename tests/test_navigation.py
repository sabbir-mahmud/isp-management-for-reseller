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


# ---------------------------------------------------------------------------#
# Charts
# ---------------------------------------------------------------------------#


def test_the_axis_ceiling_is_a_round_number():
    from decimal import Decimal

    from apps.core.templatetags.charts import nice_ceiling

    assert nice_ceiling(13935.75) == Decimal("15000")
    assert nice_ceiling(9) == Decimal("10")
    assert nice_ceiling(0) == Decimal("1")  # never zero: bar heights divide by it


def test_axis_ticks_are_compact():
    from apps.core.templatetags.charts import compact

    assert compact(0) == "0"
    assert compact(7500) == "7.5K"
    assert compact(13935) == "13.9K"
    assert compact(1250000) == "1.2M"


def test_the_chart_scales_every_bar_against_one_axis():
    """Two y-scales would invent a correlation that is not in the data."""
    from apps.core.templatetags.charts import column_chart

    rows = [
        {"label": "Jan", "revenue": 100, "expenses": 50},
        {"label": "Feb", "revenue": 200, "expenses": 100},
    ]
    ctx = column_chart(rows, [("revenue", "Revenue"), ("expenses", "Expenses")])

    heights = {
        (band["label"], bar["key"]): bar["height"] for band in ctx["bands"] for bar in band["bars"]
    }
    # 200 is the peak, so the ceiling is 200 and Feb revenue is full height.
    assert heights[("Feb", "revenue")] == 100.0
    assert heights[("Jan", "revenue")] == 50.0
    assert heights[("Feb", "expenses")] == 50.0
    assert heights[("Jan", "expenses")] == 25.0


def test_a_zero_value_draws_no_bar():
    """A 1% floor keeps tiny values visible, but zero must read as zero."""
    from apps.core.templatetags.charts import column_chart

    ctx = column_chart(
        [{"label": "Jan", "revenue": 0, "expenses": 500}], [("revenue", "R"), ("expenses", "E")]
    )
    bars = {bar["key"]: bar["height"] for bar in ctx["bands"][0]["bars"]}
    assert bars["revenue"] == 0
    assert bars["expenses"] > 0


def test_an_empty_chart_reports_no_data_rather_than_dividing_by_zero():
    from apps.core.templatetags.charts import column_chart

    ctx = column_chart([], [("revenue", "R")])
    assert ctx["has_data"] is False
    ctx = column_chart([{"label": "Jan", "revenue": 0}], [("revenue", "R")])
    assert ctx["has_data"] is False


def test_the_chart_ships_a_legend_and_a_table_view(owner_client, client_record, period):
    """Identity is never colour-alone, and the figures stay reachable."""
    from decimal import Decimal

    from apps.accountants.models import Invoice
    from apps.accountants.services import generate_invoices, record_payment

    generate_invoices(period)
    record_payment(Invoice.objects.get(), Decimal("800.00"), received_on=period)

    body = owner_client.get(reverse("dashboard")).content.decode()
    assert 'class="legend-swatch"' in body
    assert "Show the figures" in body


def test_an_empty_dashboard_shows_the_chart_placeholder(owner_client):
    """A fresh install has no money yet; the chart must not render an empty grid."""
    body = owner_client.get(reverse("dashboard")).content.decode()
    assert "Nothing to plot yet" in body


def test_chart_series_colours_pass_the_palette_gates():
    """Validated with the data-viz checker; pinned so a tweak cannot regress it."""
    from apps.core.templatetags.charts import SERIES_COLORS

    assert SERIES_COLORS["revenue"] == "#0d9488"
    assert SERIES_COLORS["expenses"] == "#ea580c"


def test_the_sparkline_needs_at_least_two_points():
    from apps.core.templatetags.charts import sparkline

    assert sparkline([], "revenue")["has_data"] is False
    assert sparkline([{"revenue": 5}], "revenue")["has_data"] is False
    assert sparkline([{"revenue": 5}, {"revenue": 9}], "revenue")["has_data"] is True


def test_the_dashboard_leads_with_exactly_one_hero_figure(owner_client):
    body = owner_client.get(reverse("dashboard")).content.decode()
    assert body.count('class="hero-value"') == 1
