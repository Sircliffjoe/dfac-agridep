from rest_framework import serializers
from agridep.apps.inputs.models import (
    InputSupplier,
    InputCatalogItem,
    InputOrder,
    InputOrderItem,
)


class InputSupplierSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)

    class Meta:
        model = InputSupplier
        fields = [
            'id', 'supplier_name', 'category', 'category_display',
            'contact_name', 'phone', 'email', 'state', 'lga',
            'warehouse_address', 'rc_number', 'is_verified', 'rating'
        ]


class InputCatalogItemSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.supplier_name', read_only=True)
    enterprise_name = serializers.CharField(source='enterprise_type.name', read_only=True, allow_null=True)

    class Meta:
        model = InputCatalogItem
        fields = [
            'id', 'supplier', 'supplier_name', 'enterprise_type', 'enterprise_name',
            'item_name', 'item_code', 'unit_of_measure', 'unit_price_naira',
            'in_stock', 'specifications'
        ]


class InputOrderItemSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='catalog_item.item_name', read_only=True)
    unit_of_measure = serializers.CharField(source='catalog_item.unit_of_measure', read_only=True)

    class Meta:
        model = InputOrderItem
        fields = [
            'id', 'catalog_item', 'item_name', 'unit_of_measure',
            'quantity', 'unit_price_naira', 'total_price_naira'
        ]


class InputOrderSerializer(serializers.ModelSerializer):
    farmer_name = serializers.SerializerMethodField()
    supplier_name = serializers.CharField(source='supplier.supplier_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    items = InputOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = InputOrder
        fields = [
            'id', 'order_code', 'farmer', 'farmer_name', 'farm',
            'supplier', 'supplier_name', 'loan', 'tranche',
            'status', 'status_display', 'total_amount_naira',
            'ordered_at', 'dispatched_at', 'delivered_at',
            'delivery_confirmation_channel', 'waybill_number',
            'delivery_notes', 'items'
        ]

    def get_farmer_name(self, obj):
        return f"{obj.farmer.first_name} {obj.farmer.last_name}"
