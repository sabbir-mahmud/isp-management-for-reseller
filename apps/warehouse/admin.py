from django.contrib import admin

from .models import Category, Onu, Pop, Product, StockMovement


@admin.register(Pop)
class PopAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "parent", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "address")
    autocomplete_fields = ("parent",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    fields = ("kind", "quantity", "reason", "reference", "occurred_on")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "quantity", "unit_price", "status", "is_low")
    list_filter = ("status", "category")
    search_fields = ("name", "model", "sku")
    list_select_related = ("category",)
    readonly_fields = ("quantity",)
    inlines = [StockMovementInline]

    @admin.display(boolean=True, description="Low stock")
    def is_low(self, obj):
        return obj.is_low


@admin.register(Onu)
class OnuAdmin(admin.ModelAdmin):
    list_display = ("serial", "model", "status", "purchase_price", "purchased_on")
    list_filter = ("status", "model")
    search_fields = ("serial", "name", "model")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "kind", "quantity", "occurred_on", "reference")
    list_filter = ("kind", "occurred_on")
    search_fields = ("product__name", "reference")
    list_select_related = ("product",)
