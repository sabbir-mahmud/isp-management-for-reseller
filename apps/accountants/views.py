import calendar

from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView, DeleteView, UpdateView

from apps.accounts.models import Clients
from apps.warehouse.models import Onu

from .forms import CommissionForm, EarnForm, InvestForm, MonthForm, YearForm
from .models import Commission, Earn, Invest, Month, Year

#----------------------------#
# Period helpers
#----------------------------#

def current_period():
    """Return the (Month, Year) rows for today, creating them if missing.

    Month/Year are user-managed lookup tables, so a fresh install has none.
    Creating on demand keeps the dashboard from 500ing on first load.
    """
    today = timezone.localdate()
    month, _ = Month.objects.get_or_create(name=calendar.month_name[today.month])
    year, _ = Year.objects.get_or_create(name=str(today.year))
    return month, year


def mark_active(month, year):
    """Flag the given rows active and clear the flag everywhere else."""
    Month.objects.exclude(pk=month.pk).filter(active=True).update(active=False)
    Month.objects.filter(pk=month.pk, active=False).update(active=True)
    Year.objects.exclude(pk=year.pk).filter(active=True).update(active=False)
    Year.objects.filter(pk=year.pk, active=False).update(active=True)


def previous_period(month, year):
    """Return the (Month, Year) preceding the given pair, or (None, None)."""
    today = timezone.localdate()
    prev_month_no = today.month - 1 or 12
    prev_year_no = today.year - 1 if today.month == 1 else today.year
    return (
        Month.objects.filter(name=calendar.month_name[prev_month_no]).first(),
        Year.objects.filter(name=str(prev_year_no)).first(),
    )


def period_total(model, field, month, year):
    """Sum `field` over the rows of `model` in the given period (0 when empty)."""
    if month is None or year is None:
        return 0
    return model.objects.filter(month=month, year=year).aggregate(
        total=Sum(field)
    )["total"] or 0


#----------------------------#
# ISP Owner Dashboard
#----------------------------#


@login_required(login_url='login')
def dashboard(request):
    month, year = current_period()
    mark_active(month, year)

    # A single Commission row drives the reseller's cut; seed it on first load.
    commission_row, _ = Commission.objects.get_or_create(pk=1)
    commission = commission_row.commission

    # client counts, in one query instead of three
    client_counts = Clients.objects.aggregate(
        total=Count('pk'),
        active=Count('pk', filter=Q(status='active')),
        inactive=Count('pk', filter=Q(status='inactive')),
    )

    # onu counts, likewise
    onu_counts = Onu.objects.aggregate(
        total=Count('pk'),
        active=Count('pk', filter=Q(status='Active')),
        stored=Count('pk', filter=Q(status='Stored')),
        damaged=Count('pk', filter=Q(status='Damaged')),
    )

    # billing
    collected_bill = Clients.objects.filter(status='active').aggregate(
        total=Sum('pack__price')
    )['total'] or 0
    profit_via_bill = (collected_bill * commission) / 100
    upstream_bill = collected_bill - profit_via_bill

    # lifetime profit
    earn = Earn.objects.aggregate(total=Sum('earn_amount'))['total'] or 0
    invest = Invest.objects.aggregate(total=Sum('invest_amount'))['total'] or 0
    profit = f'loss {invest - earn}' if earn < invest else earn - invest

    prev_month, prev_year = previous_period(month, year)

    context = {
        "clients": client_counts['total'],
        "activeClients": client_counts['active'],
        "inactiveClients": client_counts['inactive'],
        "onu": onu_counts['total'],
        "activeOnu": onu_counts['active'],
        "storedOnu": onu_counts['stored'],
        "damagedOnu": onu_counts['damaged'],
        "collected_bill": collected_bill,
        "profit_via_bill": profit_via_bill,
        "upsteam_bill": upstream_bill,
        "earn": earn,
        "invest": invest,
        "profit": profit,
        "this_month_invest": period_total(Invest, 'invest_amount', month, year),
        "this_month_earn": period_total(Earn, 'earn_amount', month, year),
        "previous_month_invest": period_total(
            Invest, 'invest_amount', prev_month, prev_year),
        "previous_month_earn": period_total(
            Earn, 'earn_amount', prev_month, prev_year),
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
    template_name = 'accountants/month_update.html'
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
    template_name = 'accountants/invest_add_form.html'
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
    template_name = 'accountants/invest_update_form.html'
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
    template_name = 'accountants/earn_add_form.html'
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
    template_name = 'accountants/earn_add_form.html'
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
    commission, _ = Commission.objects.get_or_create(pk=1)
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
