# imports
from django.shortcuts import render
from django.core.paginator import Paginator
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import Category, Product, Onu
from .filters import WarehouseProductFilter, WarehouseOnuFilter
from .forms import WarehouseProductForm, WarehouseOnuForm, CategoryForm
# Create your views here.

# -------------------------------------------------#
# Warehouse product category view
# -------------------------------------------------#


@login_required(login_url='login')
def category_list(request):
    category = Category.objects.all()
    context = {'category': category}
    return render(request, 'warehouse/category_list.html', context)


#---------------------------------------------------#
# Category create view
#---------------------------------------------------#
class CategoryCreateView(SuccessMessageMixin, CreateView):
    form_class = CategoryForm
    template_name = 'warehouse/category_add_form.html'
    success_url = '/warehouse/category'
    success_message = 'category was created'
    error_message = 'category was not created'

#---------------------------------------------------#
# Category update view
#---------------------------------------------------#


class CategoryUpdateView(SuccessMessageMixin, UpdateView):
    model = Category
    form_class = CategoryForm
    template_name = 'warehouse/category_update_form.html'
    success_url = '/warehouse/category'
    success_message = 'category was updated'
    error_message = 'category was not updated'


#---------------------------------------------#
# Category delete view
#---------------------------------------------#

class CategoryDeleteView(SuccessMessageMixin, DeleteView):
    model = Category
    template_name = 'warehouse/category_delete_confirm.html'
    success_url = '/warehouse/category'
    success_message = 'category was deleted'
    error_message = 'category was not deleted'


#------------------------------------#
# Warehouse products Views
#------------------------------------#


@login_required(login_url='login')
def warehouse_view(request):
    products = Product.objects.all().order_by('-id')
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
@method_decorator(login_required(login_url='login'), name='dispatch')
class WarehouseProductAddView(SuccessMessageMixin, CreateView):
    template_name = 'warehouse/warehouse_add.html'
    form_class = WarehouseProductForm
    success_url = '/warehouse'
    success_message = 'Product added successfully'
    error_message = 'Product not added'


#------------------------------------#
# Warehouse product update Views
#------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class WarehouseProductUpdateView(SuccessMessageMixin, UpdateView):
    model = Product
    template_name = 'warehouse/warehouse_update.html'
    form_class = WarehouseProductForm
    success_url = '/warehouse'
    success_message = 'Product added successfully'
    error_message = 'Product not added'


#------------------------------------#
# Warehouse product delete Views
#------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class WarehouseProductDeleteView(SuccessMessageMixin, DeleteView):
    model = Product
    template_name = 'warehouse/warehouse_delete.html'
    success_url = '/warehouse'
    success_message = 'Product deleted successfully'
    error_message = 'Product not deleted'


#------------------------------------#
# Onu views
# showing all onu
#------------------------------------#
@login_required(login_url='login')
def onu_view(request):
    onu = Onu.objects.all().order_by('-id')
    filter = WarehouseOnuFilter(request.GET, queryset=onu)
    onus = filter.qs
    paginator = Paginator(onus, 25)
    page_number = request.GET.get('paginator')
    onus = paginator.get_page(page_number)
    context = {'onus': onus, 'filter': filter}
    return render(request, 'onu/onu.html', context)


#------------------------------------#
# Onu add views
#------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class WarehouseOnuAddView(SuccessMessageMixin, CreateView):
    template_name = 'onu/onu_add.html'
    form_class = WarehouseOnuForm
    success_url = '/onu'
    success_message = 'Onu added successfully'
    error_message = 'Onu not added'


#------------------------------------#
# Onu update views
#------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class WarehouseOnuUpdateView(SuccessMessageMixin, UpdateView):
    model = Onu
    template_name = 'onu/onu_update.html'
    form_class = WarehouseOnuForm
    success_url = '/onu'
    success_message = 'Onu added successfully'
    error_message = 'Onu not added'

#------------------------------------#
# Onu delete views
#------------------------------------#


@method_decorator(login_required(login_url='login'), name='dispatch')
class WarehouseOnuDeleteView(SuccessMessageMixin, DeleteView):
    model = Onu
    template_name = 'onu/onu_delete.html'
    success_url = '/onu'
    success_message = 'Onu deleted successfully'
    error_message = 'Onu not deleted'
