# -----------------------------------#
# root url
# -----------------------------------#

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('warehouse/', include('apps.warehouse.urls')),
    path('', include('apps.accounts.urls')),
]
