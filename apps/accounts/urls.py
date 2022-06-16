#-----------------------------------#
# accounts urls
#-----------------------------------#
from django.urls import path, include
from . import views

urlpatterns = [
    # clients details urls
    path('', views.clients_view, name='clients'),
    path('add/', views.ClientsCreateView.as_view(), name='clients_add'),
    path('update/<str:pk>', views.ClientsUpdateView.as_view(), name='clients_update'),
    path('delete/<str:pk>', views.ClientsDeleteView.as_view(), name='clients_delete'),
    # package details urls
    path('package/', views.package_view, name="package"),

    # login urls
    path('login/', views.login_view, name='login'),
]
