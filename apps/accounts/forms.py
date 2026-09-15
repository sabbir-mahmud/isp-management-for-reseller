from django.forms import ModelForm

from .models import Clients, Package

# -----------------------------------#
# Clients form
# -----------------------------------#


class ClientsForm(ModelForm):
    class Meta:
        model = Clients
        fields = ['name', 'email', 'phone', 'nid', 'address', 'ip',
                  'pack', 'onu', 'status', 'pop_name']


class PackageForm(ModelForm):
    class Meta:
        model = Package
        fields = ['name', 'speed', 'ggc', 'fna', 'price', 'active']
