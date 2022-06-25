from django.db import models

#-----------------------------------#
# month model
#-----------------------------------#


class Month(models.Model):
    name = models.CharField(max_length=50)
    active = models.BooleanField(default=False)

    def __str__(self):
        return self.name

#-----------------------------------#
# year model
#-----------------------------------#


class Year(models.Model):
    name = models.CharField(max_length=50)
    active = models.BooleanField(default=False)

    def __str__(self):
        return self.name

#-----------------------------------#
# invest model
#-----------------------------------#


class Invest(models.Model):
    invest_details = models.CharField(max_length=250)
    invest_amount = models.DecimalField(max_digits=10, decimal_places=2)
    month = models.ForeignKey(Month, on_delete=models.CASCADE)
    year = models.ForeignKey(Year, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.invest_details

#-----------------------------------#
# earn model
#-----------------------------------#


class Earn(models.Model):
    earn_details = models.CharField(max_length=250)
    earn_amount = models.DecimalField(max_digits=10, decimal_places=2)
    month = models.ForeignKey(Month, on_delete=models.CASCADE)
    year = models.ForeignKey(Year, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.earn_details

#------------------------------------#
# commission model
#------------------------------------#


class Commission(models.Model):
    commission = models.DecimalField(
        default=20, max_digits=4, decimal_places=2)

    def __str__(self):
        return f"{self.commission}"
