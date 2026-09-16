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
    """Format an amount for display: `৳ 1,250.00`, `\u2212৳ 947.25`.

    The sign leads the symbol. Formatting the raw Decimal instead strands it
    between them — `৳ -947.25` — which reads as a typo in a column of figures.
    """
    try:
        amount = Decimal(value or 0)
    except TypeError, ValueError, InvalidOperation:
        return value
    sign = "\u2212" if amount < 0 else ""
    return f"{sign}{symbol} {abs(amount):,.2f}"


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
def initials(value, limit=2):
    """First letters of the first couple of words, for an avatar chip."""
    words = [word for word in str(value or "").split() if word]
    return "".join(word[0] for word in words[:limit]).upper() or "?"


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


@register.filter
def age(value, today=None):
    """How long ago a date was, in the one or two units that matter.

    "12 days", "5 months", "2 years 3 months". `timesince` says the same but
    joins its parts with non-breaking spaces and commas that are awkward to
    trim, and never says "today".
    """
    import datetime as dt

    from django.utils import timezone

    if not isinstance(value, dt.date):
        return ""
    if isinstance(value, dt.datetime):
        value = value.date()
    today = today or timezone.localdate()
    days = (today - value).days
    if days < 1:
        return "today"
    if days < 31:
        return f"{days} day{'s' if days != 1 else ''}"

    months = (today.year - value.year) * 12 + today.month - value.month
    if today.day < value.day:
        months -= 1
    months = max(months, 1)
    years, months = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    return " ".join(parts)


@register.filter
def absolute(value):
    """The size of a number without its sign, for templates that print their own."""
    try:
        return abs(value)
    except TypeError:
        return value
