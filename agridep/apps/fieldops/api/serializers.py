from rest_framework import serializers
from agridep.apps.fieldops.models import (
    FarmVisit,
    Inspection,
    InspectionPhoto,
    IncidentReport,
    VisitAssignment,
)


class InspectionPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionPhoto
        fields = [
            'id',
            'inspection',
            'photo',
            'caption',
            'category',
            'latitude',
            'longitude',
            'is_geofence_verified',
            'distance_to_farm_meters',
            'captured_at',
            'created_at',
        ]
        read_only_fields = ['id', 'is_geofence_verified', 'distance_to_farm_meters', 'created_at']


class InspectionSerializer(serializers.ModelSerializer):
    photos = InspectionPhotoSerializer(many=True, read_only=True)

    class Meta:
        model = Inspection
        fields = [
            'id',
            'reference_code',
            'visit',
            'produce_batch',
            'inspection_type',
            'compliance_rating',
            'water_ph',
            'water_temperature_celsius',
            'dissolved_oxygen_mg_l',
            'ammonia_ppm',
            'average_sample_weight_grams',
            'daily_mortality_count',
            'feed_inventory_kg',
            'checklist_scores',
            'biosecurity_protocol_followed',
            'corrective_actions',
            'summary_findings',
            'photos',
            'created_at',
        ]
        read_only_fields = ['id', 'reference_code', 'created_at']


class FarmVisitSerializer(serializers.ModelSerializer):
    inspections = InspectionSerializer(many=True, read_only=True)
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    farmer_name = serializers.CharField(source='farm.farmer.full_name', read_only=True)
    officer_name = serializers.CharField(source='officer.get_full_name', read_only=True)

    class Meta:
        model = FarmVisit
        fields = [
            'id',
            'reference_code',
            'farm',
            'farm_name',
            'farmer_name',
            'officer',
            'officer_name',
            'scheduled_date',
            'actual_visit_date',
            'status',
            'purpose',
            'farmer_present',
            'latitude',
            'longitude',
            'gps_accuracy_meters',
            'is_geofence_verified',
            'distance_to_farm_meters',
            'officer_notes',
            'farmer_feedback',
            'linked_assignment',
            'inspections',
            'client_id',
            'client_updated_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'reference_code',
            'is_geofence_verified',
            'distance_to_farm_meters',
            'created_at',
            'updated_at',
        ]


class IncidentReportSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    farmer_name = serializers.CharField(source='farm.farmer.full_name', read_only=True)
    reported_by_name = serializers.CharField(source='reported_by.get_full_name', read_only=True)

    class Meta:
        model = IncidentReport
        fields = [
            'id',
            'reference_code',
            'farm',
            'farm_name',
            'farmer_name',
            'produce_batch',
            'reported_by',
            'reported_by_name',
            'incident_type',
            'severity',
            'status',
            'title',
            'description',
            'immediate_actions_taken',
            'mortality_estimate',
            'financial_loss_estimate_ngn',
            'reported_at',
            'resolved_at',
            'resolved_by',
            'resolution_notes',
            'created_at',
        ]
        read_only_fields = ['id', 'reference_code', 'created_at']


class VisitAssignmentSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source='farm.name', read_only=True)
    farmer_name = serializers.CharField(source='farm.farmer.full_name', read_only=True)
    officer_name = serializers.CharField(source='assigned_officer.get_full_name', read_only=True)

    class Meta:
        model = VisitAssignment
        fields = [
            'id',
            'reference_code',
            'farm',
            'farm_name',
            'farmer_name',
            'assigned_officer',
            'officer_name',
            'due_date',
            'priority_score',
            'priority_level',
            'trigger_reason',
            'status',
            'auto_generated',
            'scoring_breakdown',
            'instructions',
            'created_at',
        ]
        read_only_fields = ['id', 'reference_code', 'created_at']
