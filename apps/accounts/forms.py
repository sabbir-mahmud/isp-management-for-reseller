from django.forms import ModelForm
from .models import Clients, Package

# -----------------------------------#
# Clients form
# -----------------------------------#


class ClientsForm(ModelForm):
    class Meta:
        model = Clients
        fields = '__all__'


class PackageForm(ModelForm):
    class Meta:
        model = Package
        fields = '__all__'
