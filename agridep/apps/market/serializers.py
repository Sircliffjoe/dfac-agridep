from rest_framework import serializers
from agridep.apps.market.models import (
    BuyerDemand,
    ProduceMatch,
    OfftakeTransaction,
    CommodityPrice,
    MatchStatus,
)


class CommodityPriceSerializer(serializers.ModelSerializer):
    enterprise_name = serializers.CharField(source='enterprise_type.name', read_only=True)

    class Meta:
        model = CommodityPrice
        fields = [
            'id',
            'enterprise_type',
            'enterprise_name',
            'market_hub',
            'state',
            'price_per_kg_naira',
            'effective_date',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class BuyerDemandSerializer(serializers.ModelSerializer):
    buyer_company_name = serializers.CharField(source='buyer.company_name', read_only=True)
    enterprise_name = serializers.CharField(source='enterprise_type.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    remaining_unmatched_volume_kg = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = BuyerDemand
        fields = [
            'id',
            'reference_code',
            'buyer',
            'buyer_company_name',
            'enterprise_type',
            'enterprise_name',
            'target_volume_kg',
            'fulfilled_volume_kg',
            'remaining_unmatched_volume_kg',
            'offered_price_per_kg_naira',
            'minimum_grade',
            'target_delivery_window_start',
            'target_delivery_window_end',
            'delivery_state',
            'delivery_lga',
            'delivery_address',
            'delivery_latitude',
            'delivery_longitude',
            'max_delivery_radius_km',
            'status',
            'status_display',
            'special_requirements',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reference_code', 'fulfilled_volume_kg', 'remaining_unmatched_volume_kg', 'created_at', 'updated_at']


class ProduceMatchSerializer(serializers.ModelSerializer):
    buyer_company_name = serializers.CharField(source='buyer_demand.buyer.company_name', read_only=True)
    produce_type_name = serializers.CharField(source='produce_batch.produce_type.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_value_naira = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    
    # NDPA Row-Scoping & Masking Fields
    producer_identity = serializers.SerializerMethodField()
    producer_phone = serializers.SerializerMethodField()
    farm_location = serializers.SerializerMethodField()

    class Meta:
        model = ProduceMatch
        fields = [
            'id',
            'reference_code',
            'buyer_demand',
            'buyer_company_name',
            'produce_batch',
            'produce_type_name',
            'allocated_volume_kg',
            'agreed_price_per_kg_naira',
            'total_value_naira',
            'distance_km',
            'status',
            'status_display',
            'declined_reason',
            'producer_identity',
            'producer_phone',
            'farm_location',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reference_code', 'total_value_naira', 'created_at', 'updated_at']

    def _is_unmasked_allowed(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        if user.is_superuser or getattr(user, 'role', '') in ['DFAC_ADMIN', 'FIELD_OFFICER']:
            return True
        # Commercial buyer can see real PII ONLY after contract is confirmed/contracted
        if getattr(user, 'role', '') == 'BUYER':
            return obj.status in [MatchStatus.CONTRACTED, MatchStatus.FULFILLED]
        return False

    def get_producer_identity(self, obj):
        farmer = obj.produce_batch.farm.farmer
        if self._is_unmasked_allowed(obj):
            return farmer.full_name
        return f"Smallholder Producer #{farmer.reference_code or farmer.id}"

    def get_producer_phone(self, obj):
        farmer = obj.produce_batch.farm.farmer
        if self._is_unmasked_allowed(obj):
            return farmer.phone_normalized
        return "[Masked until Match Confirmed]"

    def get_farm_location(self, obj):
        farm = obj.produce_batch.farm
        farmer = farm.farmer
        if self._is_unmasked_allowed(obj):
            return f"{farm.name} • {farmer.community_address}, {farmer.lga}, {farmer.state}"
        return f"Verified Farm ({farmer.lga}, {farmer.state})"


class OfftakeTransactionSerializer(serializers.ModelSerializer):
    buyer_company_name = serializers.CharField(source='match.buyer_demand.buyer.company_name', read_only=True)
    produce_type_name = serializers.CharField(source='match.produce_batch.produce_type.name', read_only=True)
    farmer_name = serializers.CharField(source='match.produce_batch.farm.farmer.full_name', read_only=True)
    farmer_phone = serializers.CharField(source='match.produce_batch.farm.farmer.phone_normalized', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = OfftakeTransaction
        fields = [
            'id',
            'reference_code',
            'waybill_number',
            'match',
            'buyer_company_name',
            'produce_type_name',
            'farmer_name',
            'farmer_phone',
            'actual_delivered_volume_kg',
            'actual_price_per_kg_naira',
            'total_amount_naira',
            'delivery_date',
            'payment_status',
            'payment_status_display',
            'quality_inspector',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reference_code', 'waybill_number', 'created_at', 'updated_at']
