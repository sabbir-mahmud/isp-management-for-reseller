"""Presentation helpers used across the templates."""

from decimal import Decimal, InvalidOperation

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """Rebuild the current query string with `kwargs` applied.

    Pagination links have to preserve active filters; hardcoding `?page=N`
    (as the old templates did) silently dropped every search term on page 2.
    Passing `None` removes a key.
    """
    params = context["request"].GET.copy()
    for key, value in kwargs.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    params.pop("_", None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else ""


@register.filter
def money(value, symbol="৳"):
    """Format an amount for display: `৳ 1,250.00`, negatives included."""
    try:
        amount = Decimal(value or 0)
    except TypeError, ValueError, InvalidOperation:
        return value
    return f"{symbol} {amount:,.2f}"


BADGES = {
    "active": "success",
    "paid": "success",
    "in_stock": "success",
    "pending": "secondary",
    "draft": "secondary",
    "unassigned": "secondary",
    "assigned": "info",
    "partial": "warning",
    "suspended": "warning",
    "reserved": "warning",
    "overdue": "danger",
    "inactive": "danger",
    "faulty": "danger",
    "cancelled": "dark",
    "terminated": "dark",
    "retired": "dark",
}


@register.filter
def status_badge(value):
    """Render a status string as a coloured pill."""
    key = str(value or "").lower().replace(" ", "_")
    tone = BADGES.get(key, "secondary")
    label = str(value or "").replace("_", " ").title()
    return mark_safe(f'<span class="badge text-bg-{tone}">{label}</span>')


@register.filter
def percent(value):
    try:
        return f"{float(value or 0):.1f}%"
    except TypeError, ValueError:
        return value


@register.filter
def subtract(value, arg):
    try:
        return Decimal(value or 0) - Decimal(arg or 0)
    except TypeError, ValueError, InvalidOperation:
        return value
