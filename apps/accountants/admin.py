from django.contrib import admin

from .models import (
    BillingSettings,
    Expense,
    Income,
    Invoice,
    InvoiceLine,
    Payment,
    UpstreamSettlement,
)


@admin.register(BillingSettings)
class BillingSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "collection_mode",
        "upstream_name",
        "commission_percent",
        "invoice_prefix",
        "due_days",
        "auto_generate",
    )

    def has_add_permission(self, request):
        # Singleton: the row is created on first load, never added by hand.
        return not BillingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 0
    readonly_fields = ("line_total",)


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("amount", "method", "received_on", "reference")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "client",
        "period",
        "total",
        "amount_paid",
        "commission_amount",
        "collection_mode",
        "status",
    )
    list_filter = ("status", "collection_mode", "period")
    search_fields = ("number", "client__name", "client__client_code")
    list_select_related = ("client",)
    autocomplete_fields = ("client", "subscription")
    readonly_fields = ("number", "total", "amount_paid", "commission_amount", "upstream_amount")
    inlines = [InvoiceLineInline, PaymentInline]
    date_hierarchy = "period"


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "invoice",
        "client",
        "amount",
        "commission_amount",
        "collection_mode",
        "method",
        "received_on",
    )
    list_filter = ("collection_mode", "method", "received_on")
    search_fields = ("invoice__number", "client__name", "reference")
    list_select_related = ("invoice", "client")
    autocomplete_fields = ("invoice",)
    date_hierarchy = "received_on"


@admin.register(UpstreamSettlement)
class UpstreamSettlementAdmin(admin.ModelAdmin):
    list_display = ("kind", "amount", "period", "settled_on", "reference")
    list_filter = ("kind", "period")
    search_fields = ("reference", "note")
    date_hierarchy = "settled_on"


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("description", "category", "amount", "occurred_on")
    list_filter = ("category", "occurred_on")
    search_fields = ("description", "note")
    date_hierarchy = "occurred_on"


@admin.register(Income)
class IncomeAdmin(admin.ModelAdmin):
    list_display = ("description", "source", "amount", "occurred_on")
    list_filter = ("source", "occurred_on")
    search_fields = ("description", "note")
    date_hierarchy = "occurred_on"
