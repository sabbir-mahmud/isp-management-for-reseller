# -----------------------------------#
# warehouse urls
# -----------------------------------#

from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.warehouse_view, name='warehouse'),
    path('add', views.WarehouseProductAddView.as_view(), name='warehouse_add'),
    path('update/<str:pk>', views.WarehouseProductUpdateView.as_view(),
         name='warehouse_update'),
    path('delete/<str:pk>', views.WarehouseProductDeleteView.as_view(),
         name='warehouse_delete'),
    path('onus', views.onu_view, name='onu'),
    path('onus_add', views.WarehouseOnuAddView.as_view(), name='onu_add'),
    path('onus_edit/<str:pk>', views.WarehouseOnuUpdateView.as_view(), name='onu_edit'),
    path('onus_del/<str:pk>', views.WarehouseOnuDeleteView.as_view(), name='onu_del'),
]
