from rest_framework import serializers
from .models import ProductionCycle, ProductionLog, ProduceBatch, HarvestForecast
from .services import process_production_log

class HarvestForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = HarvestForecast
        fields = '__all__'

class ProduceBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProduceBatch
        fields = '__all__'
        read_only_fields = ['id', 'reference_code', 'created_at', 'updated_at']

class ProductionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductionLog
        fields = '__all__'
        read_only_fields = ['id', 'reference_code', 'created_at', 'updated_at']

    def create(self, validated_data):
        log = ProductionLog.objects.create(**validated_data)
        process_production_log(log)
        return log

class ProductionCycleSerializer(serializers.ModelSerializer):
    logs = ProductionLogSerializer(many=True, read_only=True)
    produce_batches = ProduceBatchSerializer(many=True, read_only=True)
    forecast = HarvestForecastSerializer(read_only=True)

    class Meta:
        model = ProductionCycle
        fields = [
            'id', 'reference_code', 'farm', 'enterprise_type', 'cycle_name',
            'start_date', 'projected_harvest_date', 'actual_harvest_date',
            'initial_stock_count', 'current_stock_count',
            'initial_average_weight_g', 'current_average_weight_g',
            'status', 'logs', 'produce_batches', 'forecast',
            'client_id', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reference_code', 'current_stock_count', 'current_average_weight_g', 'created_at', 'updated_at']
