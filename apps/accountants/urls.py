from django.urls import path

from . import views

urlpatterns = [
    path("invoices/", views.InvoiceListView.as_view(), name="invoice_list"),
    path("invoices/add/", views.InvoiceCreateView.as_view(), name="invoice_add"),
    path("invoices/generate/", views.GenerateInvoicesView.as_view(), name="invoice_generate"),
    path("invoices/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice_detail"),
    path("invoices/<int:pk>/edit/", views.InvoiceUpdateView.as_view(), name="invoice_edit"),
    path("invoices/<int:pk>/cancel/", views.InvoiceCancelView.as_view(), name="invoice_cancel"),
    path("invoices/<int:pk>/pay/", views.PaymentCreateView.as_view(), name="payment_add"),
    path("payments/", views.PaymentListView.as_view(), name="payment_list"),
    path("payments/<int:pk>/delete/", views.PaymentDeleteView.as_view(), name="payment_delete"),
    path("expenses/", views.ExpenseListView.as_view(), name="expense_list"),
    path("expenses/add/", views.ExpenseCreateView.as_view(), name="expense_add"),
    path("expenses/<int:pk>/edit/", views.ExpenseUpdateView.as_view(), name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.ExpenseDeleteView.as_view(), name="expense_delete"),
    path("income/", views.IncomeListView.as_view(), name="income_list"),
    path("income/add/", views.IncomeCreateView.as_view(), name="income_add"),
    path("income/<int:pk>/edit/", views.IncomeUpdateView.as_view(), name="income_edit"),
    path("income/<int:pk>/delete/", views.IncomeDeleteView.as_view(), name="income_delete"),
    path("upstream/", views.SettlementListView.as_view(), name="settlement_list"),
    path("upstream/add/", views.SettlementCreateView.as_view(), name="settlement_add"),
    path(
        "upstream/<int:pk>/delete/",
        views.SettlementDeleteView.as_view(),
        name="settlement_delete",
    ),
    path("settings/", views.BillingSettingsView.as_view(), name="billing_settings"),
]
