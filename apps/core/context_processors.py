"""Template context available on every page."""

from django.conf import settings
from django.core.cache import cache


def site(request):
    """Branding + the signed-in user's role, for the shared layout."""
    profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_INITIALS": _initials(settings.SITE_NAME),
        "CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL,
        "current_role": profile.get_role_display() if profile else "",
    }


def _initials(value: str, limit: int = 2) -> str:
    """First letters of the first couple of words, for the brand mark."""
    words = [word for word in str(value or "").split() if word]
    return "".join(word[0] for word in words[:limit]).upper() or "??"


NAV_BADGE_TTL = 60


def nav_badges(request):
    """Counts shown against the sidebar links.

    Cached for a minute and skipped entirely for users without the permission
    to see the underlying page, so the navigation never costs a signed-in
    support technician a query they cannot act on.
    """
    user = request.user
    if not user.is_authenticated:
        return {}

    badges = {}
    if user.has_perm("accountants.view_invoice"):
        badges["overdue_invoices"] = cache.get_or_set(
            "nav:overdue_invoices", _overdue_invoices, NAV_BADGE_TTL
        )
    if user.has_perm("warehouse.view_product"):
        badges["low_stock"] = cache.get_or_set("nav:low_stock", _low_stock, NAV_BADGE_TTL)
    return {"nav_badges": badges}


def _overdue_invoices() -> int:
    from apps.accountants.models import Invoice

    return Invoice.objects.filter(status=Invoice.Status.OVERDUE).count()


def _low_stock() -> int:
    from apps.warehouse.models import Product

    return Product.objects.low_stock().count()
