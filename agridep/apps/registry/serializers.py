from rest_framework import serializers
from .models import EnterpriseType, Cohort, Farmer, Farm, Buyer

class EnterpriseTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnterpriseType
        fields = '__all__'

class CohortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cohort
        fields = '__all__'

class FarmSerializer(serializers.ModelSerializer):
    enterprise_type_details = EnterpriseTypeSerializer(source='enterprise_types', many=True, read_only=True)

    class Meta:
        model = Farm
        fields = [
            'id', 'reference_code', 'farmer', 'name',
            'latitude', 'longitude', 'community',
            'total_area_hectares', 'number_of_ponds', 'total_water_surface_sqm',
            'water_source', 'enterprise_types', 'enterprise_type_details',
            'client_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reference_code', 'created_at', 'updated_at']

class FarmerSerializer(serializers.ModelSerializer):
    farms = FarmSerializer(many=True, read_only=True)
    nin = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Farmer
        fields = [
            'id', 'reference_code', 'user', 'first_name', 'last_name', 'full_name',
            'gender', 'dob', 'household_size', 'primary_language',
            'phone_normalized', 'nin', 'state', 'lga', 'community_address',
            'cohort', 'assigned_officer', 'verification_status',
            'duplicate_review_notes', 'farms', 'client_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reference_code', 'verification_status', 'duplicate_review_notes', 'created_at', 'updated_at']

    def create(self, validated_data):
        raw_nin = validated_data.pop('nin', '')
        farmer = Farmer.objects.create(**validated_data)
        if raw_nin:
            farmer.set_nin(raw_nin)
            farmer.save(update_fields=['nin_encrypted', 'nin_hash'])
        return farmer

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            # Mask PII for Buyers prior to deal match confirmation
            if getattr(request.user, 'role', '') == 'BUYER':
                ret['first_name'] = 'Smallholder'
                ret['last_name'] = f"#{instance.reference_code[-4:]}"
                ret['full_name'] = f"Smallholder #{instance.reference_code[-4:]}"
                ret['phone_normalized'] = '[Protected Contact]'
                ret['community_address'] = '[Protected Address]'
        return ret

class BuyerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Buyer
        fields = '__all__'
        read_only_fields = ['id', 'reference_code', 'created_at', 'updated_at']
