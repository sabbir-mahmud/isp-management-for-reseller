from django.contrib import admin
from .models import Category, Product, Onu, Pop

# Register your models here.
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Onu)
admin.site.register(Pop)
