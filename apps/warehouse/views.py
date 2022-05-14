from itertools import product
from django.shortcuts import render
from django.core.paginator import Paginator
from django.views.generic.edit import FormView, CreateView, UpdateView, DeleteView
from django.contrib.messages.views import SuccessMessageMixin
from .models import Product
from .filters import WarehouseProductFilter
from .forms import WarehouseProductForm
# Create your views here.
#------------------------------------#
# Warehouse products Views
#------------------------------------#


def warehouse_view(request):
    products = Product.objects.all()
    filter = WarehouseProductFilter(request.GET, queryset=products)
    products = filter.qs
    paginator = Paginator(products, 25)
    page_number = request.GET.get('paginator')
    products = paginator.get_page(page_number)
    context = {'products': products, 'filter': filter}
    return render(request, 'warehouse/warehouse.html', context)


#------------------------------------#
# Warehouse product add Views
#------------------------------------#

class WarehouseProductAddView(SuccessMessageMixin, CreateView):
    template_name = 'warehouse/warehouse_add.html'
    form_class = WarehouseProductForm
    success_url = '/warehouse'
    success_message = 'Product added successfully'
    error_message = 'Product not added'


#------------------------------------#
# Warehouse product update Views
#------------------------------------#

class WarehouseProductUpdateView(SuccessMessageMixin, UpdateView):
    model = Product
    template_name = 'warehouse/warehouse_add.html'
    form_class = WarehouseProductForm
    success_url = '/warehouse'
    success_message = 'Product added successfully'
    error_message = 'Product not added'


#------------------------------------#
# Warehouse product delete Views
#------------------------------------#

class WarehouseProductDeleteView(SuccessMessageMixin, DeleteView):
    model = Product
    template_name = 'warehouse/warehouse_delete.html'
    success_url = '/warehouse'
    success_message = 'Product deleted successfully'
    error_message = 'Product not deleted'
