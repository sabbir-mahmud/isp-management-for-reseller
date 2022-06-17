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
    path('package/create', views.Package_CreateView.as_view(), name="package-add"),
    path('package/update/<str:pk>',
         views.Package_UpdateView.as_view(), name="package-update"),
    path('package/delete/<str:pk>',
         views.Package_DeleteView.as_view(), name="package-delete"),

    # login urls
    path('login/', views.login_view, name='login'),
]
