from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from agridep.apps.common.permissions import ScopedQuerySetMixin, IsDFACAdmin, IsTrainer
from agridep.apps.audit.services import log_audit_event
from agridep.apps.training.models import (
    TrainingProgramme,
    TrainingSession,
    Attendance,
    Assessment,
    Certificate,
)
from agridep.apps.training.serializers import (
    TrainingProgrammeSerializer,
    TrainingSessionSerializer,
    AttendanceSerializer,
    AssessmentSerializer,
    CertificateSerializer,
)
from agridep.apps.training.services import (
    evaluate_certification_eligibility,
    issue_certificate,
    verify_certificate_credential,
    import_bulk_attendance,
)
from agridep.apps.registry.models import Farmer


class TrainingProgrammeViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = TrainingProgramme.objects.filter(is_active=True).select_related('enterprise_type')
    serializer_class = TrainingProgrammeSerializer
    permission_classes = [IsAuthenticated]


class TrainingSessionViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = TrainingSession.objects.all().select_related('programme', 'trainer', 'cohort')
    serializer_class = TrainingSessionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', '')
        if role == 'TRAINER':
            return qs.filter(trainer=user)
        return qs

    @action(detail=True, methods=['get'])
    def eligibility_roster(self, request, pk=None):
        """
        Returns all smallholder trainees enrolled in this session along with
        their attendance percentages, assessment scores, and certification eligibility status.
        """
        session = self.get_object()
        
        # Unique farmers who attended
        farmer_ids = session.attendances.values_list('farmer_id', flat=True).distinct()
        farmers = Farmer.objects.filter(id__in=farmer_ids)
        
        roster = []
        for farmer in farmers:
            eligibility = evaluate_certification_eligibility(session, farmer)
            cert = Certificate.objects.filter(session=session, farmer=farmer).first()
            roster.append({
                'farmer_id': str(farmer.id),
                'farmer_name': farmer.full_name,
                'farmer_code': farmer.reference_code,
                'farmer_lga': farmer.lga,
                'eligibility': eligibility,
                'has_certificate': cert is not None,
                'certificate_number': cert.certificate_number if cert else None,
            })
            
        return Response({
            'session_id': str(session.id),
            'session_code': session.reference_code,
            'programme': session.programme.title,
            'total_trainees': len(roster),
            'roster': roster
        })


class AttendanceViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Attendance.objects.all().select_related('session', 'farmer')
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', '')
        if role == 'TRAINER':
            return qs.filter(session__trainer=user)
        return qs

    @action(detail=False, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def bulk_import(self, request):
        """
        Upload legacy CSV or Excel file containing attendance records.
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response(
                {'error': 'No file provided. Please upload a CSV or XLSX file under form key "file".'},
                status=status.HTTP_400_BAD_REQUEST
            )

        default_session_id = request.data.get('session_id')
        try:
            summary = import_bulk_attendance(
                file_bytes=file_obj.read(),
                file_name=file_obj.name,
                default_session_id=default_session_id,
                recorded_by=request.user
            )
            return Response(summary, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class AssessmentViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Assessment.objects.all().select_related('session', 'farmer', 'assessor')
    serializer_class = AssessmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', '')
        if role == 'TRAINER':
            return qs.filter(session__trainer=user)
        return qs

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(assessor=user)


class CertificateViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Certificate.objects.all().select_related('farmer', 'programme', 'session')
    serializer_class = CertificateSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def generate(self, request):
        """
        Evaluates eligibility and issues a secure, verifiable PDF certificate with QR code.
        """
        session_id = request.data.get('session_id')
        farmer_id = request.data.get('farmer_id')
        force = request.data.get('force', False)

        if not session_id or not farmer_id:
            return Response(
                {'error': 'Both session_id and farmer_id are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        session = get_object_or_404(TrainingSession, id=session_id)
        farmer = get_object_or_404(Farmer, id=farmer_id)

        try:
            cert = issue_certificate(
                session=session,
                farmer=farmer,
                issued_by=request.user,
                force=force
            )
            serializer = self.get_serializer(cert)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Streams the generated PDF certificate binary."""
        cert = self.get_object()
        if not cert.pdf_file:
            # Re-render if missing
            from agridep.apps.training.services import render_certificate_pdf
            pdf_content = render_certificate_pdf(cert)
            cert.pdf_file.save(pdf_content.name, pdf_content, save=True)

        return FileResponse(
            cert.pdf_file.open('rb'),
            as_attachment=True,
            filename=f"Certificate_{cert.certificate_number}.pdf",
            content_type='application/pdf'
        )

    @action(detail=False, methods=['get'], permission_classes=[AllowAny])
    def verify(self, request):
        """
        Public or partner endpoint to verify a certificate by token or certificate number.
        """
        code = request.query_params.get('code', '').strip()
        if not code:
            return Response(
                {'error': 'Verification query parameter "code" is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        verification = verify_certificate_credential(code)
        resp_data = {
            'is_valid': verification.get('is_valid', False),
            'status': verification.get('status', 'NOT_FOUND'),
            'message': verification.get('message', ''),
            'certificate_id': str(verification['certificate'].id) if verification.get('certificate') else None,
            'details': verification.get('details', {})
        }
        if not verification['is_valid']:
            return Response(resp_data, status=status.HTTP_404_NOT_FOUND)
        return Response(resp_data, status=status.HTTP_200_OK)
