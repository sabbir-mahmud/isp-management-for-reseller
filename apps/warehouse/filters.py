import django_filters
from .models import Product, Onu

# -------------------------------------------------#
# Warehouse product filter
# -------------------------------------------------#


class WarehouseProductFilter(django_filters.FilterSet):
    class Meta:
        model = Product
        fields = ['category', 'serial', 'status']


# -------------------------------------------------#
# Onu filter
# -------------------------------------------------#


class WarehouseOnuFilter(django_filters.FilterSet):
    class Meta:
        model = Onu
        fields = ['serial', 'status']
