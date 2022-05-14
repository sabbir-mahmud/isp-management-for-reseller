from django.forms import ModelForm
from .models import Product, Onu

# -------------------------------------------------#
# Warehouse product model form
# -------------------------------------------------#


class WarehouseProductForm(ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'model', 'category',
                  'quantity', 'price', 'serial', 'status']


class WarehouseOnuForm(ModelForm):
    class Meta:
        model = Onu
        fields = ['name', 'model', 'port', 'price', 'serial', 'status']
