from django.shortcuts import redirect, render
from django.core.paginator import Paginator
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .models import Clients, Package
from .filters import ClientsFilter
from .forms import ClientsForm, PackageForm

# -----------------------------------#
# Clients views
# -----------------------------------#


@login_required(login_url='login')
def clients_view(request):
    clients = Clients.objects.all().order_by('-id')
    filter = ClientsFilter(request.GET, queryset=clients)
    clients = filter.qs
    paginator = Paginator(clients, 25)
    page_number = request.GET.get('paginator')
    clients = paginator.get_page(page_number)
    context = {'clients': clients, 'filter': filter}
    return render(request, 'accounts/clients.html', context)

# -----------------------------------#
# Clients create view
# -----------------------------------#


@method_decorator(login_required(login_url='login'), name='dispatch')
class ClientsCreateView(SuccessMessageMixin, CreateView):
    template_name = 'accounts/clients_add.html'
    form_class = ClientsForm
    success_url = '/accounts'
    success_message = 'client was created'
    error_message = 'client was not created'

# -----------------------------------#
# clients update view
# -----------------------------------#


@method_decorator(login_required(login_url='login'), name='dispatch')
class ClientsUpdateView(SuccessMessageMixin, UpdateView):
    model = Clients
    template_name = 'accounts/clients_update.html'
    form_class = ClientsForm
    success_url = '/accounts'
    success_message = 'client was updated'
    error_message = 'client was not updated'


# -----------------------------------#
# clients delete view
# -----------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class ClientsDeleteView(SuccessMessageMixin, DeleteView):
    model = Clients
    template_name = 'accounts/clients_delete.html'
    success_url = '/accounts'
    success_message = 'client was deleted'
    error_message = 'client was not deleted'


# -----------------------------------#
# package views
# -----------------------------------#
@login_required(login_url='login')
def package_view(request):
    packages = Package.objects.all().order_by('-id')
    paginator = Paginator(packages, 25)
    page_number = request.GET.get('paginator')
    packages = paginator.get_page(page_number)
    context = {'packages': packages}
    return render(request, 'package/package.html', context)

# -----------------------------------#
# package create view
# -----------------------------------#


@method_decorator(login_required(login_url='login'), name='dispatch')
class Package_CreateView(SuccessMessageMixin, CreateView):
    template_name = 'package/package_add_form.html'
    form_class = PackageForm
    success_url = '/package'
    success_message = 'package was created'
    error_message = 'client was not created'


# -----------------------------------#
# package update view
# -----------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class Package_UpdateView(SuccessMessageMixin, UpdateView):
    model = Package
    template_name = 'package/package_update_form.html'
    form_class = PackageForm
    success_url = '/package'
    success_message = 'package was updated'
    error_message = 'package was not updated'

# -----------------------------------#
# package delete view
# -----------------------------------#


@method_decorator(login_required(login_url='login'), name='dispatch')
class Package_DeleteView(SuccessMessageMixin, DeleteView):
    model = Package
    template_name = 'package/package_delete.html'
    success_url = '/package'
    success_message = 'package was deleted'
    error_message = 'package was not deleted'

# -----------------------------------#
# login view
# -----------------------------------#


def login_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if "next" in request.POST:
                return redirect(request.POST['next'])
            else:
                return redirect('clients')
        else:

            render(request, 'accounts/login.html',
                   {'error': 'username or password is incorrect'})
    return render(request, 'accounts/login.html')
