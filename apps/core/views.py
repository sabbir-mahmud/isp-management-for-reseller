"""Operational endpoints that are not part of the product UI."""

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache


@never_cache
def healthz(request):
    """Liveness + database readiness, for the load balancer.

    Deliberately unauthenticated and free of business data.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database_ok = True
    except Exception:  # pragma: no cover - only on a genuinely broken DB
        database_ok = False

    payload = {"status": "ok" if database_ok else "degraded", "database": database_ok}
    return JsonResponse(payload, status=200 if database_ok else 503)


def handler_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def handler_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def handler_500(request):
    return render(request, "errors/500.html", status=500)
