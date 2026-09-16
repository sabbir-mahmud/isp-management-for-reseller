from django.contrib import admin

from .models import Client, Package, Subscription


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("name", "bandwidth_mbps", "monthly_price", "is_active", "subscriber_count")
    list_filter = ("is_active",)
    search_fields = ("name",)


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    extra = 0
    fields = ("package", "monthly_price", "discount", "start_date", "end_date", "status")
    autocomplete_fields = ("package",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("client_code", "name", "username", "phone", "pop", "status", "created_at")
    list_filter = ("status", "pop")
    search_fields = ("client_code", "name", "username", "phone", "nid", "email")
    list_select_related = ("pop", "onu")
    autocomplete_fields = ("pop", "onu")
    readonly_fields = ("client_code", "created_at", "updated_at")
    inlines = [SubscriptionInline]
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        # The admin should still show soft-deleted rows so they can be restored.
        return Client.all_objects.select_related("pop", "onu")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("client", "package", "monthly_price", "discount", "status", "start_date")
    list_filter = ("status", "package")
    search_fields = ("client__name", "client__client_code")
    list_select_related = ("client", "package")
    autocomplete_fields = ("client", "package")
