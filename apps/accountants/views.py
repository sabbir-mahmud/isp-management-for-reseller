from django.shortcuts import render
from django.db.models import Sum
from apps.accounts.models import Clients
from apps.warehouse.models import Onu
from apps.accountants.models import Commission
from .models import Month, Year, Invest, Earn, Commission

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
