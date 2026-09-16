"""Root URL configuration.

Routes are grouped by domain rather than by app name, so the URLs read the way
the business talks: /clients/, /invoices/, /inventory/.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.core.views import healthz

urlpatterns = [
    path("", include("apps.reports.urls")),
    path("", include("apps.users.urls")),
    path("", include("apps.accounts.urls")),
    path("inventory/", include("apps.warehouse.urls")),
    path("billing/", include("apps.accountants.urls")),
    path("healthz", healthz, name="healthz"),
    path(settings.ADMIN_URL, admin.site.urls),
]

handler403 = "apps.core.views.handler_403"
handler404 = "apps.core.views.handler_404"
handler500 = "apps.core.views.handler_500"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
