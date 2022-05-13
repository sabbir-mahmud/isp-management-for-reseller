from itertools import product
from django.shortcuts import render
from django.core.paginator import Paginator
from .models import Product
from .filters import WarehouseProductFilter
# Create your views here.
#------------------------------------#
# Warehouse Views
#------------------------------------#


def warehouse_view(request):
    products = Product.objects.all()
    filter = WarehouseProductFilter(request.GET, queryset=products)
    products = filter.qs
    paginator = Paginator(products, )
    page_number = request.GET.get('paginator')
    products = paginator.get_page(page_number)
    context = {'products': products, 'filter': filter}
    return render(request, 'warehouse/warehouse.html', context)
