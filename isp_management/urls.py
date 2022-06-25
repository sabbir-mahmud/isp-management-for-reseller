# -----------------------------------#
# root url
# -----------------------------------#

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('apps.accounts.urls')),
    path('admin/', admin.site.urls),
    path('warehouse/', include('apps.warehouse.urls')),
    path('dashboard/', include('apps.accountants.urls')),
]
