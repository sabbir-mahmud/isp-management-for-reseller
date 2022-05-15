from django.db import models
from apps.warehouse.models import Onu

# Create your models here.
#-------------------------------------------------#
# Model: clients
#-------------------------------------------------#


class Clients(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    phone = models.CharField(max_length=100, verbose_name='phone')
    nid = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    ip = models.CharField(max_length=100, unique=True,
                          verbose_name='IP/UserName')
    onu = models.ForeignKey(Onu, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
