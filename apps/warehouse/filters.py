import django_filters
from .models import Product

# -------------------------------------------------#
# Warehouse product filter
# -------------------------------------------------#


class WarehouseProductFilter(django_filters.FilterSet):
    class Meta:
        model = Product
        fields = ['category', 'serial', 'status']
