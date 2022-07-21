from django.shortcuts import render
from django.db.models import Sum
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.core.paginator import Paginator
from apps.accounts.models import Clients
from apps.warehouse.models import Onu
from apps.accountants.models import Commission
from .models import Month, Year, Invest, Earn, Commission
from .forms import MonthForm, YearForm, InvestForm, EarnForm, CommissionForm

# Create your views here.

#----------------------------#
# ISP Owner Dashboard
#----------------------------#


def dashboard(request):
    # clients list details
    clients = Clients.objects.all().count()
    activeClients = Clients.objects.filter(status='active').count()
    inactiveClients = Clients.objects.filter(status='inactive').count()

    # onu list
    onu = Onu.objects.all().count()
    activeOnu = Onu.objects.filter(status="Active").count()
    storedOnu = Onu.objects.filter(status="Active").count()
    damagedOnu = Onu.objects.filter(status="Active").count()

    # earing details
    collected_bill = Clients.objects.filter(status='active').aggregate(
        Sum('pack__price'))['pack__price__sum'] if Clients.objects.filter(status='active').exists() else 0

    # commission details
    commission = Commission.objects.get(id=1)
    profit_via_bill = (collected_bill * commission.commission)/100
    upsteam_bill = collected_bill - profit_via_bill

    context = {
        "clients": clients,
        "activeClients": activeClients,
        "inactiveClients": inactiveClients,
        "onu": onu,
        "activeOnu": activeOnu,
        "storedOnu": storedOnu,
        "damagedOnu": damagedOnu,
        "collected_bill": collected_bill,
        "profit_via_bill": profit_via_bill,
        "upsteam_bill": upsteam_bill

    }
    return render(request, 'dashboard/dashboard.html', context)


#----------------------------#
# Months
#----------------------------#
def months(request):
    months = Month.objects.all()
    paginator = Paginator(months, 25)
    page_number = request.GET.get('paginator')
    months = paginator.get_page(page_number)
    context = {'months': months}
    return render(request, 'accountants/months.html', context)

# ----------------------------#
# Month Create View
# ----------------------------#


class MonthAddView(SuccessMessageMixin, CreateView):
    form_class = MonthForm
    template_name = 'accountants/month_form.html'
    success_url = '/dashboard/months'
    success_message = 'month was created'
    error_message = 'month was not created'


# ----------------------------#
# Month Update View
# ----------------------------#


class MonthUpdateView(SuccessMessageMixin, UpdateView):
    model = Month
    form_class = MonthForm
    template_name = 'accountants/month_form.html'
    success_url = '/dashboard/months'
    success_message = 'Month was updated'
    error_message = 'Month was not updated'


#---------------------------#
# Month delete
#---------------------------#

class MonthDelete(SuccessMessageMixin, DeleteView):
    model = Month
    template_name = 'accountants/month_delete_confirm.html'
    success_url = '/dashboard/months'
    success_message = 'Month was deleted'
    error_message = 'Month was not deleted'

# --------------------------------#
# Year
#---------------------------------#


def yearView(request):
    years = Year.objects.all()
    paginator = Paginator(years, 25)
    page = request.GET.get('paginator')
    years = paginator.get_page(page)
    context = {
        'years': years
    }
    return render(request, 'accountants/year.html', context)


#----------------------------------#
# Year add View
#----------------------------------#

class YearAddView(SuccessMessageMixin, CreateView):
    form_class = YearForm
    template_name = 'accountants/year_form.html'
    success_url = '/dashboard/years'
    success_message = 'Year was created'
    error_message = 'Year was not created'


#-----------------------------------#
# Year update view
#-----------------------------------#

class YearUpdateView(SuccessMessageMixin, UpdateView):
    model = Year
    form_class = YearForm
    template_name = 'accountants/year_form.html'
    success_url = '/dashboard/years'
    success_message = 'Year was updated'
    error_message = 'Year was not updated'


#------------------------------------#
# Year delete view
#------------------------------------#

class YearDeleteView(SuccessMessageMixin, DeleteView):
    model = Year
    template_name = 'accountants/year_confirm_delete.html'
    success_url = '/dashboard/years'
    success_message = 'Year was deleted'
    error_message = 'Year was not deleted'


#--------------------------------------#
# invest view
#--------------------------------------#

def investView(request):
    invests = Invest.objects.all()
    paginator = Paginator(invests, 25)
    page = request.GET.get('paginator')
    invests = paginator.get_page(page)
    context = {
        "invests": invests
    }
    return render(request, 'accountants/invest.html', context)
