from django.urls import path

from . import views

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("reports/financial/", views.FinancialReportView.as_view(), name="financial_report"),
    path("reports/export/<str:dataset>.csv", views.ExportView.as_view(), name="export"),
]
