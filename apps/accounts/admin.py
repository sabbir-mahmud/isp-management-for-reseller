from django.contrib import admin
from .models import Package, Reseller, Clients
# Register your models here.

admin.site.register(Package)
admin.site.register(Reseller)
admin.site.register(Clients)
