from django.urls import path

from . import views

urlpatterns = [
    path("clients/", views.ClientListView.as_view(), name="client_list"),
    path("clients/add/", views.ClientCreateView.as_view(), name="client_add"),
    path("clients/<int:pk>/", views.ClientDetailView.as_view(), name="client_detail"),
    path("clients/<int:pk>/edit/", views.ClientUpdateView.as_view(), name="client_edit"),
    path("clients/<int:pk>/delete/", views.ClientDeleteView.as_view(), name="client_delete"),
    path("clients/<int:pk>/status/", views.ClientStatusView.as_view(), name="client_status"),
    path("packages/", views.PackageListView.as_view(), name="package_list"),
    path("packages/add/", views.PackageCreateView.as_view(), name="package_add"),
    path("packages/<int:pk>/edit/", views.PackageUpdateView.as_view(), name="package_edit"),
    path("packages/<int:pk>/delete/", views.PackageDeleteView.as_view(), name="package_delete"),
    path("pops/", views.PopListView.as_view(), name="pop_list"),
    path("pops/add/", views.PopCreateView.as_view(), name="pop_add"),
    path("pops/<int:pk>/edit/", views.PopUpdateView.as_view(), name="pop_edit"),
    path("pops/<int:pk>/delete/", views.PopDeleteView.as_view(), name="pop_delete"),
]
