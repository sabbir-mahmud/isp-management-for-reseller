from django.forms import ModelForm

from .models import Category, Onu, Product

# -------------------------------------------------#
# Warehouse product category form
# -------------------------------------------------#


class CategoryForm(ModelForm):
    class Meta:
        model = Category
        fields = ['name']

# -------------------------------------------------#
# Warehouse product model form
# -------------------------------------------------#


class WarehouseProductForm(ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'model', 'category',
                  'quantity', 'price', 'serial', 'status']


# -------------------------------------------------#
# Warehouse Onu model form
# -------------------------------------------------#
class WarehouseOnuForm(ModelForm):
    class Meta:
        model = Onu
        fields = ['name', 'model', 'port', 'price', 'serial', 'status']
