"""Template context available on every page."""

from django.conf import settings


def site(request):
    """Branding + the signed-in user's role, for the shared layout."""
    profile = getattr(request.user, "profile", None) if request.user.is_authenticated else None
    return {
        "SITE_NAME": settings.SITE_NAME,
        "CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL,
        "current_role": profile.get_role_display() if profile else "",
    }
