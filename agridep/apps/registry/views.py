from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from agridep.apps.common.permissions import ScopedQuerySetMixin, IsDFACAdmin, IsFieldOfficer
from agridep.apps.audit.services import log_audit_event
from .models import EnterpriseType, Cohort, Farmer, Farm, Buyer, VerificationStatus
from .serializers import EnterpriseTypeSerializer, CohortSerializer, FarmerSerializer, FarmSerializer, BuyerSerializer
from .services import check_farmer_duplicates

class EnterpriseTypeViewSet(viewsets.ModelViewSet):
    queryset = EnterpriseType.objects.filter(is_active=True)
    serializer_class = EnterpriseTypeSerializer
    permission_classes = [IsAuthenticated]

class CohortViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Cohort.objects.all()
    serializer_class = CohortSerializer
    permission_classes = [IsAuthenticated]

class FarmerViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Farmer.objects.all().select_related('cohort', 'assigned_officer').prefetch_related('farms')
    serializer_class = FarmerSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        user = self.request.user
        validated_data = serializer.validated_data
        
        # Check duplicate
        is_dup, rec_status, reasons, matched = check_farmer_duplicates(
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            phone=validated_data.get('phone_normalized', ''),
            nin=validated_data.get('nin', '')
        )
        
        assigned_officer = validated_data.get('assigned_officer')
        if not assigned_officer and getattr(user, 'role', '') == 'FIELD_OFFICER':
            assigned_officer = user

        farmer = serializer.save(
            assigned_officer=assigned_officer,
            verification_status=rec_status,
            duplicate_review_notes="; ".join(reasons) if reasons else ""
        )

        log_audit_event(
            action='CREATE',
            resource_type='Farmer',
            resource_id=str(farmer.id),
            user=user,
            details={'duplicate_flag': is_dup, 'reasons': reasons},
            request=self.request
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Audit read of farmer PII
        log_audit_event(
            action='READ_SENSITIVE_PII',
            resource_type='Farmer',
            resource_id=str(instance.id),
            user=request.user,
            request=request
        )
        return super().retrieve(request, *args, **kwargs)

    @action(detail=False, methods=['post'], url_path='check-duplicate')
    def check_duplicate(self, request):
        """Pre-validation endpoint for field officers and offline app before submitting."""
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        phone = request.data.get('phone', '')
        nin = request.data.get('nin', '')
        lat = request.data.get('latitude')
        lon = request.data.get('longitude')
        
        is_dup, status_rec, reasons, matched = check_farmer_duplicates(
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            nin=nin,
            lat=float(lat) if lat is not None else None,
            lon=float(lon) if lon is not None else None
        )
        return Response({
            "is_duplicate_or_flagged": is_dup,
            "recommended_status": status_rec,
            "reasons": reasons,
            "matched_farmer_code": matched.reference_code if matched else None
        })

class FarmViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Farm.objects.all().select_related('farmer').prefetch_related('enterprise_types')
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated]

class BuyerViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Buyer.objects.all()
    serializer_class = BuyerSerializer
    permission_classes = [IsAuthenticated]
