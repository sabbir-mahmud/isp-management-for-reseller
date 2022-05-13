# -----------------------------------#
# warehouse urls
# -----------------------------------#

from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.warehouse_view, name='warehouse'),
]
