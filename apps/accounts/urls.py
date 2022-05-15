#-----------------------------------#
# accounts urls
#-----------------------------------#
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.clients_view, name='clients'),
    path('add/', views.ClientsCreateView.as_view(), name='clients_add'),
]
