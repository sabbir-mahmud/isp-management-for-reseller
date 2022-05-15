from django.shortcuts import render
from django.core.paginator import Paginator
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from .models import Clients
from .filters import ClientsFilter
from .forms import ClientsForm

# -----------------------------------#
# Clients views
# -----------------------------------#


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


class ClientsCreateView(SuccessMessageMixin, CreateView):
    template_name = 'accounts/clients_form.html'
    form_class = ClientsForm
    success_url = '/accounts'
    success_message = 'client was created'
    error_message = 'client was not created'
