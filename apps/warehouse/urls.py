# -----------------------------------#
# warehouse urls
# -----------------------------------#

from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.warehouse_view, name='warehouse'),
    path('/add', views.WarehouseProductAddView.as_view(), name='warehouse_add'),
    path('/update/<str:pk>', views.WarehouseProductUpdateView.as_view(),
         name='warehouse_update'),
    path('/delete/<str:pk>', views.WarehouseProductDeleteView.as_view(),
         name='warehouse_delete'),
]
