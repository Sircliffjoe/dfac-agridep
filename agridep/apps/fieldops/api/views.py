from decimal import Decimal
from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from agridep.apps.accounts.models import UserRole
from agridep.apps.fieldops.models import (
    FarmVisit,
    Inspection,
    InspectionPhoto,
    IncidentReport,
    VisitAssignment,
)
from agridep.apps.fieldops.api.serializers import (
    FarmVisitSerializer,
    InspectionSerializer,
    InspectionPhotoSerializer,
    IncidentReportSerializer,
    VisitAssignmentSerializer,
)
from agridep.apps.fieldops.services import (
    verify_geofence,
    build_visit_priority_queue,
    auto_generate_visit_assignments,
)


class FieldOpsPermission(permissions.BasePermission):
    """
    RBAC Permission:
      - DFAC_ADMIN, FIELD_OFFICER, TRAINER have access.
      - FARMER has read-only access to their own farm records.
      - LENDER, BUYER are strictly forbidden (RBAC isolation).
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser or request.user.role in [UserRole.DFAC_ADMIN, UserRole.FIELD_OFFICER, UserRole.TRAINER]:
            return True
        if request.user.role == UserRole.FARMER and request.method in permissions.SAFE_METHODS:
            return True
        return False


class FarmVisitViewSet(viewsets.ModelViewSet):
    serializer_class = FarmVisitSerializer
    permission_classes = [FieldOpsPermission]
    filterset_fields = ['farm', 'officer', 'status', 'purpose', 'is_geofence_verified']
    search_fields = ['reference_code', 'farm__name', 'officer_notes']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return FarmVisit.objects.none()
        if user.is_superuser or user.role == UserRole.DFAC_ADMIN:
            return FarmVisit.objects.select_related('farm', 'farm__farmer', 'officer').all()
        if user.role == UserRole.FIELD_OFFICER:
            return FarmVisit.objects.select_related('farm', 'farm__farmer', 'officer').filter(
                Q(officer=user) | Q(farm__farmer__assigned_officer=user) | Q(farm__farmer__lga=user.lga)
            )
        if user.role == UserRole.FARMER:
            return FarmVisit.objects.select_related('farm', 'farm__farmer', 'officer').filter(
                farm__farmer__user=user
            )
        return FarmVisit.objects.none()

    def perform_create(self, serializer):
        visit = serializer.save(officer=self.request.user)
        # Verify geofence if coordinates are provided
        if visit.latitude is not None and visit.longitude is not None:
            is_verified, distance = verify_geofence(visit.farm, visit.latitude, visit.longitude)
            visit.is_geofence_verified = is_verified
            visit.distance_to_farm_meters = distance
            visit.save(update_fields=['is_geofence_verified', 'distance_to_farm_meters'])


class InspectionViewSet(viewsets.ModelViewSet):
    serializer_class = InspectionSerializer
    permission_classes = [FieldOpsPermission]
    filterset_fields = ['visit', 'produce_batch', 'inspection_type', 'compliance_rating']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Inspection.objects.none()
        if user.is_superuser or user.role == UserRole.DFAC_ADMIN:
            return Inspection.objects.select_related('visit', 'visit__farm').all()
        if user.role == UserRole.FIELD_OFFICER:
            return Inspection.objects.select_related('visit', 'visit__farm').filter(
                Q(visit__officer=user) | Q(visit__farm__farmer__lga=user.lga)
            )
        if user.role == UserRole.FARMER:
            return Inspection.objects.select_related('visit', 'visit__farm').filter(
                visit__farm__farmer__user=user
            )
        return Inspection.objects.none()


class InspectionPhotoViewSet(viewsets.ModelViewSet):
    serializer_class = InspectionPhotoSerializer
    permission_classes = [FieldOpsPermission]

    def get_queryset(self):
        return InspectionPhoto.objects.select_related('inspection', 'inspection__visit').all()

    def perform_create(self, serializer):
        photo = serializer.save()
        farm = photo.inspection.visit.farm
        if photo.latitude is not None and photo.longitude is not None:
            is_verified, distance = verify_geofence(farm, photo.latitude, photo.longitude)
            photo.is_geofence_verified = is_verified
            photo.distance_to_farm_meters = distance
            photo.save(update_fields=['is_geofence_verified', 'distance_to_farm_meters'])


class IncidentReportViewSet(viewsets.ModelViewSet):
    serializer_class = IncidentReportSerializer
    permission_classes = [FieldOpsPermission]
    filterset_fields = ['farm', 'severity', 'status', 'incident_type']
    search_fields = ['reference_code', 'title', 'description']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return IncidentReport.objects.none()
        if user.is_superuser or user.role == UserRole.DFAC_ADMIN:
            return IncidentReport.objects.select_related('farm', 'reported_by').all()
        if user.role == UserRole.FIELD_OFFICER:
            return IncidentReport.objects.select_related('farm', 'reported_by').filter(
                Q(reported_by=user) | Q(farm__farmer__assigned_officer=user) | Q(farm__farmer__lga=user.lga)
            )
        if user.role == UserRole.FARMER:
            return IncidentReport.objects.select_related('farm', 'reported_by').filter(
                farm__farmer__user=user
            )
        return IncidentReport.objects.none()

    def perform_create(self, serializer):
        serializer.save(reported_by=self.request.user)


class VisitAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = VisitAssignmentSerializer
    permission_classes = [FieldOpsPermission]
    filterset_fields = ['assigned_officer', 'status', 'priority_level', 'trigger_reason']

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return VisitAssignment.objects.none()
        if user.is_superuser or user.role == UserRole.DFAC_ADMIN:
            return VisitAssignment.objects.select_related('farm', 'assigned_officer').all()
        if user.role == UserRole.FIELD_OFFICER:
            return VisitAssignment.objects.select_related('farm', 'assigned_officer').filter(
                assigned_officer=user
            )
        return VisitAssignment.objects.none()


class PriorityQueueAPIView(APIView):
    """
    Dynamic ranking endpoint for extension visits.
    Recalculates real-time priority scores based on dynamic parameters.
    """
    permission_classes = [FieldOpsPermission]

    def get(self, request):
        officer = request.user if request.user.role == UserRole.FIELD_OFFICER else None
        lga = request.query_params.get('lga', None)
        limit = int(request.query_params.get('limit', 50))

        queue = build_visit_priority_queue(officer=officer, lga=lga, limit=limit)
        return Response({
            'count': len(queue),
            'results': queue
        })

    def post(self, request):
        """Trigger automated dispatch of VisitAssignments based on priority queue."""
        min_threshold = Decimal(str(request.data.get('min_priority_threshold', '25.00')))
        officer = request.user if request.user.role == UserRole.FIELD_OFFICER else None

        assignments = auto_generate_visit_assignments(
            officer=officer,
            min_priority_threshold=min_threshold
        )

        return Response({
            'message': f"Successfully generated {len(assignments)} visit assignments.",
            'assignments_count': len(assignments),
            'assignments': VisitAssignmentSerializer(assignments, many=True).data
        }, status=status.HTTP_201_CREATED)
