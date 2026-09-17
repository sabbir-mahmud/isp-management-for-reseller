from django.urls import path

from . import views

urlpatterns = [
    path("stock/", views.ProductListView.as_view(), name="product_list"),
    path("stock/add/", views.ProductCreateView.as_view(), name="product_add"),
    path("stock/<int:pk>/edit/", views.ProductUpdateView.as_view(), name="product_edit"),
    path("stock/<int:pk>/delete/", views.ProductDeleteView.as_view(), name="product_delete"),
    path("categories/", views.CategoryListView.as_view(), name="category_list"),
    path("categories/add/", views.CategoryCreateView.as_view(), name="category_add"),
    path("categories/<int:pk>/edit/", views.CategoryUpdateView.as_view(), name="category_edit"),
    path("categories/<int:pk>/delete/", views.CategoryDeleteView.as_view(), name="category_delete"),
    path("onus/", views.OnuListView.as_view(), name="onu_list"),
    path("onus/add/", views.OnuCreateView.as_view(), name="onu_add"),
    path("onus/<int:pk>/edit/", views.OnuUpdateView.as_view(), name="onu_edit"),
    path("onus/<int:pk>/delete/", views.OnuDeleteView.as_view(), name="onu_delete"),
    path("movements/", views.StockMovementListView.as_view(), name="movement_list"),
    path("movements/add/", views.StockMovementCreateView.as_view(), name="movement_add"),
]
