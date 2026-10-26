from decimal import Decimal
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from agridep.apps.common.permissions import ScopedQuerySetMixin, IsDFACAdmin, IsLender
from agridep.apps.registry.models import Farmer
from agridep.apps.finance.models import (
    Lender,
    LoanRecord,
    LoanTranche,
    RepaymentSchedule,
    Repayment,
    RiskFlag,
    CreditScoreSnapshot,
)
from agridep.apps.finance.serializers import (
    LenderSerializer,
    LoanRecordSerializer,
    LoanTrancheSerializer,
    RepaymentScheduleSerializer,
    RepaymentSerializer,
    RiskFlagSerializer,
)
from agridep.apps.finance.services import (
    calculate_loan_expected_value_and_risk,
    evaluate_loan_credit_score,
    calculate_multi_season_credit_score,
    disburse_loan_facility,
    release_tranche_gate,
    record_repayment_transaction,
)


class LenderViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Lender.objects.filter(is_active=True)
    serializer_class = LenderSerializer
    permission_classes = [IsAuthenticated]


class LoanRecordViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = LoanRecord.objects.all().select_related('farmer', 'lender', 'farm', 'production_cycle').prefetch_related('tranches', 'risk_flags')
    serializer_class = LoanRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        role = getattr(user, 'role', '')

        # Strict RBAC: Buyers and Trainers DENIED loan portfolio data
        if role in ['BUYER', 'TRAINER']:
            return qs.none()

        if role == 'LENDER':
            return qs.filter(lender__user=user)
        elif role == 'FARMER':
            return qs.filter(farmer__user=user)
        return qs

    @action(detail=True, methods=['get'])
    def risk_analysis(self, request, pk=None):
        """
        Runs the transparent expected-value and risk model (RULE-02, RULE-03).
        Calculates harvest coverage ratio, yield deficit risk, and repayment arrears.
        """
        loan = self.get_object()
        analysis = calculate_loan_expected_value_and_risk(loan)
        return Response({
            'loan_code': loan.reference_code,
            'farmer_name': loan.farmer.full_name,
            'expected_harvest_value_naira': float(analysis['expected_harvest_value']),
            'outstanding_balance_naira': float(analysis['outstanding_balance']),
            'coverage_ratio': float(analysis['coverage_ratio']),
            'risk_level': analysis['risk_level'],
            'loan_status': analysis['loan_status'],
            'active_flags_count': len(analysis['flags_raised']),
        })

    @action(detail=True, methods=['post'])
    def disburse(self, request, pk=None):
        """Disburses credit facility and initiates installment schedules."""
        loan = self.get_object()
        try:
            disburse_loan_facility(loan, disbursed_by=request.user)
            serializer = self.get_serializer(loan)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def credit_score(self, request, pk=None):
        """Evaluates transparent rule-based credit scoring (RULE-05 certification bonus)."""
        loan = self.get_object()
        target_enterprise = loan.production_cycle.enterprise_type if loan.production_cycle else None
        score_eval = evaluate_loan_credit_score(loan.farmer, target_enterprise)
        loan.credit_score = score_eval['credit_score']
        loan.save(update_fields=['credit_score', 'updated_at'])
        return Response(score_eval, status=status.HTTP_200_OK)


class LoanTrancheViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = LoanTranche.objects.all().select_related('loan')
    serializer_class = LoanTrancheSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        """Enforces RULE-08 input delivery confirmation stage gate before releasing tranche."""
        tranche = self.get_object()
        bypass_gate = request.data.get('bypass_gate', False)
        try:
            release_tranche_gate(tranche, released_by=request.user, bypass_gate=bypass_gate)
            serializer = self.get_serializer(tranche)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class RepaymentViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = Repayment.objects.all().select_related('loan', 'schedule')
    serializer_class = RepaymentSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        loan_id = request.data.get('loan_id') or request.data.get('loan')
        amount = Decimal(str(request.data.get('amount_naira', '0.00')))
        method = request.data.get('payment_method', 'BANK_TRANSFER')
        ref = request.data.get('transaction_reference')
        notes = request.data.get('notes', '')

        if not loan_id or amount <= Decimal('0.00'):
            return Response(
                {'error': 'loan_id and a positive amount_naira are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        loan = get_object_or_404(LoanRecord, id=loan_id)
        repayment = record_repayment_transaction(
            loan=loan,
            amount_naira=amount,
            payment_method=method,
            transaction_reference=ref,
            notes=notes,
            recorded_by=request.user
        )
        serializer = self.get_serializer(repayment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class RiskFlagViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    queryset = RiskFlag.objects.all().select_related('loan', 'farmer', 'production_cycle')
    serializer_class = RiskFlagSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        flag = self.get_object()
        flag.is_resolved = True
        flag.resolved_at = timezone.now()
        flag.resolved_by = request.user
        flag.save()
        return Response({'status': 'Risk flag resolved successfully.'}, status=status.HTTP_200_OK)


class CreditScoreAPIView(APIView):
    """Calculates or retrieves the latest multi-season credit score snapshot for a smallholder."""
    permission_classes = [IsAuthenticated]

    def get(self, request, farmer_id):
        farmer = get_object_or_404(Farmer, pk=farmer_id)
        latest = CreditScoreSnapshot.objects.filter(farmer=farmer).first()
        if not latest or request.query_params.get('recalculate') == 'true':
            latest = calculate_multi_season_credit_score(farmer)
        
        return Response({
            'farmer_id': str(farmer.id),
            'farmer_name': f"{farmer.first_name} {farmer.last_name}",
            'score': latest.score,
            'rating_tier': latest.rating_tier,
            'rating_tier_display': latest.get_rating_tier_display(),
            'recommended_credit_limit_naira': float(latest.recommended_credit_limit_naira),
            'pillars': {
                'repayment': float(latest.repayment_score),
                'biometrics': float(latest.biometric_score),
                'certification': float(latest.certification_score),
                'inspection': float(latest.inspection_score),
                'stability': float(latest.stability_score),
            },
            'breakdown': latest.explanation_breakdown,
            'assessed_date': str(latest.assessed_date)
        }, status=status.HTTP_200_OK)

