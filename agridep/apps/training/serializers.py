from rest_framework import serializers
from agridep.apps.training.models import (
    TrainingProgramme,
    TrainingSession,
    Attendance,
    Assessment,
    Certificate,
)
from agridep.apps.registry.models import EnterpriseType, Farmer, Cohort


class TrainingProgrammeSerializer(serializers.ModelSerializer):
    enterprise_type_name = serializers.CharField(source='enterprise_type.name', read_only=True)

    class Meta:
        model = TrainingProgramme
        fields = [
            'id',
            'reference_code',
            'title',
            'enterprise_type',
            'enterprise_type_name',
            'description',
            'curriculum_summary',
            'duration_days',
            'min_attendance_pct',
            'min_pass_score',
            'validity_months',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reference_code', 'created_at', 'updated_at']


class TrainingSessionSerializer(serializers.ModelSerializer):
    programme_title = serializers.CharField(source='programme.title', read_only=True)
    trainer_name = serializers.CharField(source='trainer.get_full_name', read_only=True)
    total_scheduled_days = serializers.IntegerField(read_only=True)
    attendance_count = serializers.SerializerMethodField()
    certified_count = serializers.SerializerMethodField()

    class Meta:
        model = TrainingSession
        fields = [
            'id',
            'reference_code',
            'programme',
            'programme_title',
            'trainer',
            'trainer_name',
            'cohort',
            'venue',
            'lga',
            'state',
            'start_date',
            'end_date',
            'max_capacity',
            'status',
            'total_scheduled_days',
            'attendance_count',
            'certified_count',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'reference_code', 'total_scheduled_days', 'created_at', 'updated_at']

    def get_attendance_count(self, obj):
        return obj.attendances.values('farmer').distinct().count()

    def get_certified_count(self, obj):
        return obj.certificates.filter(is_valid=True).count()


class AttendanceSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)
    farmer_code = serializers.CharField(source='farmer.reference_code', read_only=True)
    session_code = serializers.CharField(source='session.reference_code', read_only=True)

    class Meta:
        model = Attendance
        fields = [
            'id',
            'session',
            'session_code',
            'farmer',
            'farmer_name',
            'farmer_code',
            'date',
            'status',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class AssessmentSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)
    farmer_code = serializers.CharField(source='farmer.reference_code', read_only=True)
    session_code = serializers.CharField(source='session.reference_code', read_only=True)

    class Meta:
        model = Assessment
        fields = [
            'id',
            'session',
            'session_code',
            'farmer',
            'farmer_name',
            'farmer_code',
            'score',
            'max_score',
            'passed',
            'assessment_date',
            'feedback',
            'created_at',
        ]
        read_only_fields = ['id', 'passed', 'created_at']


class CertificateSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)
    farmer_code = serializers.CharField(source='farmer.reference_code', read_only=True)
    programme_title = serializers.CharField(source='programme.title', read_only=True)
    session_venue = serializers.CharField(source='session.venue', read_only=True)
    pdf_url = serializers.SerializerMethodField()
    qr_code_url = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'id',
            'certificate_number',
            'verification_code',
            'farmer',
            'farmer_name',
            'farmer_code',
            'programme',
            'programme_title',
            'session',
            'session_venue',
            'issue_date',
            'expiry_date',
            'is_valid',
            'pdf_url',
            'qr_code_url',
            'created_at',
        ]
        read_only_fields = ['id', 'certificate_number', 'verification_code', 'is_valid', 'created_at']

    def get_pdf_url(self, obj):
        if obj.pdf_file:
            return obj.pdf_file.url
        return None

    def get_qr_code_url(self, obj):
        if obj.qr_code_image:
            return obj.qr_code_image.url
        return None
