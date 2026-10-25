from rest_framework import serializers
from agridep.apps.finance.models import (
    Lender,
    LoanRecord,
    LoanTranche,
    RepaymentSchedule,
    Repayment,
    RiskFlag,
)


class LenderSerializer(serializers.ModelSerializer):
    institution_type_name = serializers.CharField(source='get_institution_type_display', read_only=True)

    class Meta:
        model = Lender
        fields = [
            'id',
            'reference_code',
            'institution_name',
            'institution_type',
            'institution_type_name',
            'contact_person',
            'phone',
            'email',
            'operating_states',
            'concessionary_rate_pct',
            'is_active',
            'created_at',
        ]
        read_only_fields = ['id', 'reference_code', 'created_at']


class LoanTrancheSerializer(serializers.ModelSerializer):
    tranche_type_display = serializers.CharField(source='get_tranche_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = LoanTranche
        fields = [
            'id',
            'reference_code',
            'loan',
            'tranche_number',
            'amount_naira',
            'tranche_type',
            'tranche_type_display',
            'milestone_conditions',
            'status',
            'status_display',
            'disbursement_date',
            'input_order_reference',
            'created_at',
        ]
        read_only_fields = ['id', 'reference_code', 'created_at']


class RepaymentScheduleSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = RepaymentSchedule
        fields = [
            'id',
            'loan',
            'installment_number',
            'due_date',
            'expected_amount_naira',
            'paid_amount_naira',
            'status',
            'status_display',
            'paid_date',
        ]
        read_only_fields = ['id']


class RepaymentSerializer(serializers.ModelSerializer):
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)

    class Meta:
        model = Repayment
        fields = [
            'id',
            'loan',
            'schedule',
            'amount_naira',
            'payment_date',
            'payment_method',
            'payment_method_display',
            'transaction_reference',
            'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class RiskFlagSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)
    loan_reference = serializers.CharField(source='loan.reference_code', read_only=True)

    class Meta:
        model = RiskFlag
        fields = [
            'id',
            'loan',
            'loan_reference',
            'farmer',
            'farmer_name',
            'production_cycle',
            'severity',
            'rule_triggered',
            'title',
            'description',
            'is_resolved',
            'resolved_at',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class LoanRecordSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source='farmer.full_name', read_only=True)
    farmer_code = serializers.CharField(source='farmer.reference_code', read_only=True)
    farmer_phone = serializers.CharField(source='farmer.phone_normalized', read_only=True)
    lender_name = serializers.CharField(source='lender.institution_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    total_payable_naira = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    outstanding_balance_naira = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    tranches = LoanTrancheSerializer(many=True, read_only=True)
    risk_flags = RiskFlagSerializer(many=True, read_only=True)

    class Meta:
        model = LoanRecord
        fields = [
            'id',
            'reference_code',
            'farmer',
            'farmer_name',
            'farmer_code',
            'farmer_phone',
            'lender',
            'lender_name',
            'farm',
            'production_cycle',
            'facility_name',
            'principal_amount_naira',
            'interest_rate_percent',
            'tenure_months',
            'application_date',
            'approval_date',
            'disbursement_date',
            'repayment_due_date',
            'total_repaid_naira',
            'total_payable_naira',
            'outstanding_balance_naira',
            'status',
            'status_display',
            'credit_score',
            'tranches',
            'risk_flags',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'reference_code',
            'total_repaid_naira',
            'total_payable_naira',
            'outstanding_balance_naira',
            'created_at',
            'updated_at',
        ]
