import django_filters
from .models import Clients

#------------------------------------#
# Clients filter
#------------------------------------#


class ClientsFilter(django_filters.FilterSet):
    class Meta:
        model = Clients
        fields = ['phone', 'ip']
