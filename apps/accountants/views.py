from django.shortcuts import redirect, render
from django.db.models import Sum
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from apps.accounts.models import Clients
from apps.warehouse.models import Onu
from apps.accountants.models import Commission
from .models import Month, Year, Invest, Earn, Commission
from .forms import MonthForm, YearForm, InvestForm, EarnForm, CommissionForm
import datetime
# Create your views here.

#----------------------------#
# ISP Owner Dashboard
#----------------------------#


@login_required(login_url='login')
def dashboard(request):
    #----------------------------#
    # Active Months and Years
    #----------------------------#

    def activeDate(monthID, year):
        # active month
        month = Month.objects.get(id=monthID)
        month.active = True
        month.save()
        # deactivate other months
        months = Month.objects.all().exclude(id=monthID)
        for month in months:
            month.active = False
            month.save()

        # active year
        year = Year.objects.get(name=year)
        year.active = True
        year.save()
        # deactivate other years
        years = Year.objects.all().exclude(name=year)
        for year in years:
            year.active = False
            year.save()

    # Get Month
    currentMonth = datetime.datetime.now().month
    currentYear = datetime.datetime.now().year
    activeDate(monthID=currentMonth, year=currentYear)

    # automation commission
    if Commission.objects.filter(id=1):
        pass
    else:
        Commission.objects.create()

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
    commission = Commission.objects.get(
        id=1).commission if Commission.objects.filter(id=1).exists() else 20
    profit_via_bill = (collected_bill * commission)/100
    upsteam_bill = collected_bill - profit_via_bill

    # profit details
    earn = Earn.objects.all().aggregate(Sum('earn_amount'))[
        'earn_amount__sum'] if Earn.objects.all().exists() else 0
    invest = Invest.objects.all().aggregate(Sum('invest_amount'))[
        'invest_amount__sum'] if Invest.objects.all().exists() else 0
    profit = None
    if earn < invest:
        profit = f'loss {invest - earn}'
    else:
        profit = earn - invest

    # this month details
    this_month_invest = Invest.objects.filter(
        month=currentMonth, year=currentYear).aggregate(Sum('invest_amount'))['invest_amount__sum'] if Invest.objects.filter(month=currentMonth, year=currentYear).exists() else 0

    this_month_earn = Earn.objects.filter(
        month=currentMonth, year=currentYear).aggregate(Sum('earn_amount'))['earn_amount__sum'] if Earn.objects.filter(month=currentMonth, year=currentYear).exists() else 0

    # previous month details
    previous_month_invest = Invest.objects.filter(
        month=currentMonth-1, year=currentYear).aggregate(Sum('invest_amount'))['invest_amount__sum'] if Invest.objects.filter(month=currentMonth-1, year=currentYear).exists() else 0

    previous_month_earn = Earn.objects.filter(
        month=currentMonth-1, year=currentYear).aggregate(Sum('earn_amount'))['earn_amount__sum'] if Earn.objects.filter(month=currentMonth-1, year=currentYear).exists() else 0

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
        "upsteam_bill": upsteam_bill,
        "earn": earn,
        "invest": invest,
        "profit": profit,
        "this_month_invest": this_month_invest,
        "this_month_earn": this_month_earn,
        "previous_month_invest": previous_month_invest,
        "previous_month_earn": previous_month_earn,

    }
    return render(request, 'dashboard/dashboard.html', context)


#----------------------------#
# Months
#----------------------------#
@login_required(login_url='login')
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


@method_decorator(login_required(login_url='login'), name='dispatch')
class MonthAddView(SuccessMessageMixin, CreateView):
    form_class = MonthForm
    template_name = 'accountants/month_form.html'
    success_url = '/dashboard/months'
    success_message = 'month was created'
    error_message = 'month was not created'


# ----------------------------#
# Month Update View
# ----------------------------#

@method_decorator(login_required(login_url='login'), name='dispatch')
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
@method_decorator(login_required(login_url='login'), name='dispatch')
class MonthDelete(SuccessMessageMixin, DeleteView):
    model = Month
    template_name = 'accountants/month_delete_confirm.html'
    success_url = '/dashboard/months'
    success_message = 'Month was deleted'
    error_message = 'Month was not deleted'

# --------------------------------#
# Year
#---------------------------------#


@login_required(login_url='login')
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
@method_decorator(login_required(login_url='login'), name='dispatch')
class YearAddView(SuccessMessageMixin, CreateView):
    form_class = YearForm
    template_name = 'accountants/year_form.html'
    success_url = '/dashboard/years'
    success_message = 'Year was created'
    error_message = 'Year was not created'


#-----------------------------------#
# Year update view
#-----------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
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
@method_decorator(login_required(login_url='login'), name='dispatch')
class YearDeleteView(SuccessMessageMixin, DeleteView):
    model = Year
    template_name = 'accountants/year_confirm_delete.html'
    success_url = '/dashboard/years'
    success_message = 'Year was deleted'
    error_message = 'Year was not deleted'


#--------------------------------------#
# invest view
#--------------------------------------#

@login_required(login_url='login')
def investView(request):
    invests = Invest.objects.all()
    paginator = Paginator(invests, 25)
    page = request.GET.get('paginator')
    invests = paginator.get_page(page)
    context = {
        "invests": invests
    }
    return render(request, 'accountants/invest.html', context)


#---------------------------------------#
# invest add view
#---------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class InvestAddView(SuccessMessageMixin, CreateView):
    form_class = InvestForm
    template_name = 'accountants/invest_form.html'
    success_url = '/dashboard/invests'
    success_message = 'Invest Details was created'
    error_message = 'Invest Details was not created'


#-----------------------------------------#
# invest update view
#-----------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class InvestUpdateView(SuccessMessageMixin, UpdateView):
    model = Invest
    form_class = InvestForm
    template_name = 'accountants/invest_form.html'
    success_url = '/dashboard/invests'
    success_message = 'Invest Details was updated'
    error_message = 'Invest Details was not updated'


#------------------------------------------#
# invest delete from
#------------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class InvestDeleteView(SuccessMessageMixin, DeleteView):
    model = Invest
    template_name = 'accountants/invest_delete_confirm.html'
    success_url = '/dashboard/invests'
    success_message = 'Invest Details was deleted'
    error_message = 'Invest Details was not deleted'


#-----------------------------------------#
# Earning views
#-----------------------------------------#
@login_required(login_url='login')
def earningView(request):
    earnings = Earn.objects.all()
    paginator = Paginator(earnings, 25)
    page = request.GET.get('paginator')
    earnings = paginator.get_page(page)
    context = {
        "earnings": earnings
    }
    return render(request, 'accountants/earning.html', context)


#-----------------------------------------#
# Earning add view
#-----------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class EarningAddView(SuccessMessageMixin, CreateView):
    form_class = EarnForm
    template_name = 'accountants/earn_form.html'
    success_url = '/dashboard/earnings'
    success_message = 'Earning details was created'
    error_message = 'Earning details was not created'


#------------------------------------------#
# Earning update view
#------------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class EarningUpdateView(SuccessMessageMixin, UpdateView):
    model = Earn
    form_class = EarnForm
    template_name = 'accountants/earn_form.html'
    success_url = '/dashboard/earnings'
    success_message = 'Earning details was updated'
    error_message = 'Earning details was not updated'


#--------------------------------------------#
# Earning delete view
#--------------------------------------------#
@method_decorator(login_required(login_url='login'), name='dispatch')
class EarningDeleteView(SuccessMessageMixin, DeleteView):
    model = Earn
    template_name = 'accountants/earn_delete_confirm.html'
    success_url = '/dashboard/earnings'
    success_message = 'Earnings details was deleted'
    error_message = 'Earning details was not deleted'


#--------------------------------------------#
# commission view
#--------------------------------------------#
@login_required(login_url='login')
def commissionView(request):
    commission = Commission.objects.get(id=1)
    form = CommissionForm(instance=commission)
    context = {
        "commission": commission,
        "form": form
    }
    if request.method == "POST":
        form = CommissionForm(request.POST, instance=commission)
        if form.is_valid():
            form.save()
            return redirect('dashboard')
        else:
            return render(request, 'accountants/commission.html', context)

    return render(request, 'accountants/commission.html', context)
