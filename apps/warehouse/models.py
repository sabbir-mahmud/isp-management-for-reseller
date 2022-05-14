from django.db import models

# Create your models here.

# -------------------------------------------------#
# Warehouse product category model
# -------------------------------------------------#


class Category(models.Model):
    name = models.CharField(max_length=245)

    def __str__(self):
        return self.name

# -------------------------------------------------#
# Warehouse product model
# -------------------------------------------------#


class Product(models.Model):
    choice_status = (('Active', 'Active'), ('Stored', 'Stored'),
                     ('Damaged', 'Damaged'))
    name = models.CharField(max_length=245)
    model = models.CharField(max_length=245)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price = models.FloatField()
    serial = models.CharField(max_length=245, unique=True)
    status = models.CharField(max_length=245, choices=choice_status)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
