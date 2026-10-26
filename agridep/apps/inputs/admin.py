from django.contrib import admin
from agridep.apps.inputs.models import (
    InputSupplier,
    InputCatalogItem,
    InputOrder,
    InputOrderItem,
)


class InputCatalogItemInline(admin.TabularInline):
    model = InputCatalogItem
    extra = 1


@admin.register(InputSupplier)
class InputSupplierAdmin(admin.ModelAdmin):
    list_display = ('supplier_name', 'category', 'contact_name', 'phone', 'state', 'lga', 'is_verified', 'rating')
    list_filter = ('category', 'state', 'is_verified')
    search_fields = ('supplier_name', 'contact_name', 'phone', 'email')
    inlines = [InputCatalogItemInline]


class InputOrderItemInline(admin.TabularInline):
    model = InputOrderItem
    extra = 0
    readonly_fields = ('total_price_naira',)


@admin.register(InputOrder)
class InputOrderAdmin(admin.ModelAdmin):
    list_display = (
        'order_code', 'farmer', 'supplier', 'total_amount_naira',
        'status', 'delivery_confirmation_channel', 'ordered_at', 'delivered_at'
    )
    list_filter = ('status', 'delivery_confirmation_channel', 'ordered_at')
    search_fields = ('order_code', 'farmer__first_name', 'farmer__last_name', 'supplier__supplier_name')
    inlines = [InputOrderItemInline]
    readonly_fields = ('order_code', 'ordered_at', 'dispatched_at', 'delivered_at')


@admin.register(InputCatalogItem)
class InputCatalogItemAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'item_code', 'supplier', 'enterprise_type', 'unit_of_measure', 'unit_price_naira', 'in_stock')
    list_filter = ('in_stock', 'enterprise_type', 'supplier')
    search_fields = ('item_name', 'item_code')
