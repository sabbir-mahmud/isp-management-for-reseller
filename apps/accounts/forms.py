from django.forms import ModelForm
from .models import Clients

# -----------------------------------#
# Clients form
# -----------------------------------#


class ClientsForm(ModelForm):
    class Meta:
        model = Clients
        fields = '__all__'
