from random import choices
from django.db import models
from apps.warehouse.models import Onu


#-----------------------------------#
# package model
#-----------------------------------#

class Package(models.Model):
    name = models.CharField(max_length=50)
    speed = models.CharField(max_length=50)
    ggc = models.CharField(max_length=50)
    fna = models.CharField(max_length=50)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(default=False)

    def __str__(self):
        return self.name

#-----------------------------------#
# reseller model
#-----------------------------------#


class Reseller(models.Model):
    choices_select = (('active', 'active'), ('inactive', 'inactive'))
    name = models.CharField(max_length=50)
    address = models.CharField(max_length=50)
    phone = models.CharField(max_length=50)
    nid = models.CharField(max_length=50)
    commission = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=50, choices=choices_select, default='active')

    def __str__(self):
        return self.name


#-------------------------------------------------#
# Model: clients
#-------------------------------------------------#


class Clients(models.Model):
    choices_select = (('active', 'active'), ('inactive', 'inactive'))
    name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    phone = models.CharField(max_length=100, verbose_name='phone')
    nid = models.CharField(max_length=100)
    address = models.CharField(max_length=100)
    ip = models.CharField(max_length=100, unique=True,
                          verbose_name='IP/UserName')
    pack = models.ForeignKey(Package, on_delete=models.CASCADE)
    onu = models.ForeignKey(Onu, on_delete=models.CASCADE)
    reseller = models.ForeignKey(Reseller, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=50, choices=choices_select, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
