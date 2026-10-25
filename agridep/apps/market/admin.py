from django.contrib import admin
from django.utils.html import format_html
from agridep.apps.market.models import (
    BuyerDemand,
    ProduceMatch,
    OfftakeTransaction,
    CommodityPrice,
)


@admin.register(BuyerDemand)
class BuyerDemandAdmin(admin.ModelAdmin):
    list_display = (
        'reference_code',
        'buyer',
        'enterprise_type',
        'volume_display',
        'price_display',
        'delivery_window',
        'delivery_lga',
        'status_badge'
    )
    list_filter = ('status', 'enterprise_type', 'delivery_state', 'delivery_lga')
    search_fields = ('reference_code', 'buyer__company_name')

    def volume_display(self, obj):
        return f"{obj.fulfilled_volume_kg:,.0f} / {obj.target_volume_kg:,.0f} kg"
    volume_display.short_description = "Fulfilled / Target"

    def price_display(self, obj):
        return f"₦{obj.offered_price_per_kg_naira:,.2f}/kg"
    price_display.short_description = "Offered Price"

    def delivery_window(self, obj):
        return f"{obj.target_delivery_window_start.strftime('%d %b')} - {obj.target_delivery_window_end.strftime('%d %b %Y')}"
    delivery_window.short_description = "Delivery Window"

    def status_badge(self, obj):
        colors = {
            'OPEN': '#3B82F6',
            'PARTIALLY_MATCHED': '#F59E0B',
            'FULLY_MATCHED': '#10B981',
            'CONTRACTED': '#16A34A',
            'FULFILLED': '#047857',
            'CANCELLED': '#EF4444',
            'EXPIRED': '#6B7280',
        }
        color = colors.get(obj.status, '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"


@admin.register(ProduceMatch)
class ProduceMatchAdmin(admin.ModelAdmin):
    list_display = (
        'reference_code',
        'buyer_demand',
        'allocated_volume_display',
        'agreed_price_display',
        'distance_display',
        'status_badge'
    )
    list_filter = ('status',)
    search_fields = ('reference_code', 'buyer_demand__buyer__company_name', 'produce_batch__reference_code')

    def allocated_volume_display(self, obj):
        return f"{obj.allocated_volume_kg:,.0f} kg"
    allocated_volume_display.short_description = "Allocated Volume"

    def agreed_price_display(self, obj):
        return f"₦{obj.agreed_price_per_kg_naira:,.2f}/kg (Total: ₦{obj.total_value_naira:,.2f})"
    agreed_price_display.short_description = "Value"

    def distance_display(self, obj):
        return f"{obj.distance_km} km"
    distance_display.short_description = "Logistics Distance"

    def status_badge(self, obj):
        colors = {
            'PROPOSED': '#3B82F6',
            'ACCEPTED_BY_BUYER': '#F59E0B',
            'CONFIRMED_BY_FARMER': '#10B981',
            'CONTRACTED': '#16A34A',
            'DECLINED': '#EF4444',
            'FULFILLED': '#047857',
        }
        color = colors.get(obj.status, '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Match Status"


@admin.register(OfftakeTransaction)
class OfftakeTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'waybill_number',
        'buyer_name',
        'farmer_name',
        'actual_delivered_volume_display',
        'total_amount_display',
        'delivery_date',
        'payment_status_badge'
    )
    list_filter = ('payment_status', 'delivery_date')
    search_fields = ('waybill_number', 'match__buyer_demand__buyer__company_name')

    def buyer_name(self, obj):
        return obj.match.buyer_demand.buyer.company_name
    buyer_name.short_description = "Commercial Buyer"

    def farmer_name(self, obj):
        return obj.match.produce_batch.farm.farmer.full_name
    farmer_name.short_description = "Contracted Producer"

    def actual_delivered_volume_display(self, obj):
        return f"{obj.actual_delivered_volume_kg:,.0f} kg"
    actual_delivered_volume_display.short_description = "Volume"

    def total_amount_display(self, obj):
        return f"₦{obj.total_amount_naira:,.2f}"
    total_amount_display.short_description = "Settlement Amount"

    def payment_status_badge(self, obj):
        colors = {
            'PENDING': '#F59E0B',
            'ESCROW_HELD': '#3B82F6',
            'PAID_FARMER': '#16A34A',
            'DISPUTED': '#EF4444',
        }
        color = colors.get(obj.payment_status, '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_payment_status_display()
        )
    payment_status_badge.short_description = "Escrow / Settlement"


@admin.register(CommodityPrice)
class CommodityPriceAdmin(admin.ModelAdmin):
    list_display = ('enterprise_type', 'market_hub', 'state', 'price_per_kg_display', 'effective_date')
    list_filter = ('enterprise_type', 'state')
    search_fields = ('market_hub',)

    def price_per_kg_display(self, obj):
        return f"₦{obj.price_per_kg_naira:,.2f}/kg"
    price_per_kg_display.short_description = "Spot Price"
