from django.contrib import admin

from .models import Clients, Package

# Register your models here.

admin.site.register(Package)
admin.site.register(Clients)
