from decimal import Decimal
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError

from agridep.apps.finance.models import (
    Lender,
    LoanRecord,
    LoanStatus,
    LoanTranche,
    TrancheStatus,
    RepaymentSchedule,
    ScheduleStatus,
    Repayment,
    PaymentMethod,
    RiskFlag,
    RiskSeverity,
    CreditScoreSnapshot,
    CreditRatingTier,
)
from agridep.apps.registry.models import Farmer, EnterpriseType, Farm
from agridep.apps.production.models import ProductionCycle, ProduceBatch, ProductionLog
from agridep.apps.training.models import Certificate
from agridep.apps.fieldops.models import Inspection, ComplianceRating
from agridep.apps.common.models import SystemParameter
from agridep.apps.audit.services import log_audit_event


def calculate_loan_expected_value_and_risk(loan: LoanRecord) -> Dict[str, Any]:
    """
    Transparent rule-based risk model calculating harvest coverage ratio
    and automated risk flags against loan exposure.
    
    Formula:
    Expected Harvest Value = Projected Harvest Volume (kg) * Reference Commodity Price (₦/kg)
    Coverage Ratio = Expected Harvest Value / Outstanding Balance (Principal + Interest)
    
    Operating Ranges:
    - Coverage Ratio >= 2.50: Normal low-risk operation (e.g. ₦850k harvest vs ₦200k loan = 4.25x)
    - 1.75 <= Ratio < 2.50: Moderate operating buffer
    - 1.20 <= Ratio < 1.75: Medium early-warning deficit (RULE-03)
    - Ratio < 1.20: Critical default risk (RULE-03)
    """
    outstanding_balance = loan.outstanding_balance_naira
    if outstanding_balance <= Decimal('0.00'):
        return {
            'expected_harvest_value': Decimal('0.00'),
            'outstanding_balance': Decimal('0.00'),
            'coverage_ratio': Decimal('999.0'),
            'risk_level': 'LOW',
            'flags_raised': [],
            'is_performing': True
        }

    # Determine projected harvest volume from linked cycle or farm batches
    projected_volume_kg = Decimal('0.00')
    ref_price_per_kg = Decimal('2500.00')  # fallback default

    if loan.production_cycle:
        cycle = loan.production_cycle
        if cycle.enterprise_type:
            ref_price_per_kg = cycle.enterprise_type.reference_price_per_kg_naira
        # Estimate from cycle current stock and average weight
        if cycle.current_stock_count and cycle.current_average_weight_g:
            kg_estimate = (Decimal(cycle.current_stock_count) * Decimal(cycle.current_average_weight_g)) / Decimal('1000.0')
            projected_volume_kg = max(projected_volume_kg, kg_estimate)
        # Or look up ProduceBatch
        batch = ProduceBatch.objects.filter(cycle=cycle).first()
        if batch and batch.projected_volume_kg:
            projected_volume_kg = max(projected_volume_kg, batch.projected_volume_kg)
    elif loan.farm:
        batches = ProduceBatch.objects.filter(farm=loan.farm, status__in=['FORECASTED', 'AVAILABLE'])
        for b in batches:
            projected_volume_kg += b.projected_volume_kg
            if b.produce_type:
                ref_price_per_kg = b.produce_type.reference_price_per_kg_naira

    # If still 0, use standard smallholder model (1,000kg table fish)
    if projected_volume_kg <= Decimal('0.00'):
        projected_volume_kg = Decimal('400.00')

    expected_harvest_value = projected_volume_kg * ref_price_per_kg
    coverage_ratio = round(expected_harvest_value / max(outstanding_balance, Decimal('1.00')), 2)

    flags_raised = []
    risk_level = 'LOW'

    # Check Rule 03: Coverage threshold breach
    if coverage_ratio < Decimal('1.20'):
        risk_level = 'CRITICAL'
        flag, _ = RiskFlag.objects.get_or_create(
            loan=loan,
            farmer=loan.farmer,
            rule_triggered='RULE-03',
            defaults={
                'severity': RiskSeverity.CRITICAL,
                'title': f"Critical Harvest Coverage Deficit ({coverage_ratio:.2f}x)",
                'description': f"Expected harvest value of ₦{expected_harvest_value:,.2f} is insufficient to cover outstanding balance of ₦{outstanding_balance:,.2f}. Coverage ratio is {coverage_ratio:.2f} (critical threshold < 1.20x)."
            }
        )
        flags_raised.append(flag)
        if loan.status in [LoanStatus.DISBURSED, LoanStatus.PERFORMING]:
            loan.status = LoanStatus.WATCHLIST
            loan.save(update_fields=['status', 'updated_at'])

    elif coverage_ratio < Decimal('1.75'):
        risk_level = 'MEDIUM'
        flag, _ = RiskFlag.objects.get_or_create(
            loan=loan,
            farmer=loan.farmer,
            rule_triggered='RULE-03',
            defaults={
                'severity': RiskSeverity.MEDIUM,
                'title': f"Early-Warning Yield Deficit ({coverage_ratio:.2f}x)",
                'description': f"Expected harvest value ₦{expected_harvest_value:,.2f} provides a reduced coverage buffer of {coverage_ratio:.2f}x (threshold < 1.75x)."
            }
        )
        flags_raised.append(flag)

    # Check Rule 02: Repayment arrears > 7 days past due date
    today = timezone.now().date()
    seven_days_ago = today - timedelta(days=7)
    overdue_schedules = loan.repayment_schedules.filter(
        status__in=[ScheduleStatus.PENDING, ScheduleStatus.PARTIALLY_PAID],
        due_date__lt=seven_days_ago
    )

    if overdue_schedules.exists():
        risk_level = 'HIGH' if risk_level != 'CRITICAL' else 'CRITICAL'
        for sch in overdue_schedules:
            sch.status = ScheduleStatus.OVERDUE
            sch.save(update_fields=['status', 'updated_at'])
            
            flag, _ = RiskFlag.objects.get_or_create(
                loan=loan,
                farmer=loan.farmer,
                rule_triggered='RULE-02',
                defaults={
                    'severity': RiskSeverity.HIGH,
                    'title': f"Loan Repayment Arrears: Installment #{sch.installment_number} Overdue",
                    'description': f"Installment #{sch.installment_number} of ₦{sch.expected_amount_naira:,.2f} due on {sch.due_date} is more than 7 days overdue."
                }
            )
            flags_raised.append(flag)
        
        loan.status = LoanStatus.DELINQUENT
        loan.save(update_fields=['status', 'updated_at'])

    return {
        'expected_harvest_value': expected_harvest_value,
        'outstanding_balance': outstanding_balance,
        'coverage_ratio': coverage_ratio,
        'risk_level': risk_level,
        'flags_raised': flags_raised,
        'loan_status': loan.status
    }


def evaluate_loan_credit_score(farmer: Farmer, enterprise_type: Optional[EnterpriseType] = None) -> Dict[str, Any]:
    """
    Transparent rule-based credit scoring model (RULE-05):
    - Base score: 65.0 pts
    - Active valid Certificate in target enterprise: +15.0 pts (RULE-05)
    - Verified smallholder status: +10.0 pts
    - Unresolved active RiskFlags: -20.0 pts
    """
    score = Decimal('65.00')
    factors = []

    # Check Rule 05: Certificate bonus
    certs_query = Certificate.objects.filter(farmer=farmer, is_valid=True)
    if enterprise_type:
        certs_query = certs_query.filter(programme__enterprise_type=enterprise_type)

    has_cert = certs_query.exists()
    if has_cert:
        score += Decimal('15.00')
        factors.append("RULE-05: +15 pts for holding accredited DFAC capacity building certificate.")

    if farmer.verification_status == 'VERIFIED':
        score += Decimal('10.00')
        factors.append("+10 pts for verified smallholder identity and farm location.")

    active_risks = RiskFlag.objects.filter(farmer=farmer, is_resolved=False).count()
    if active_risks > 0:
        deduction = Decimal(min(active_risks * 10, 20))
        score -= deduction
        factors.append(f"-{deduction} pts penalty for {active_risks} active unresolved risk flag(s).")

    final_score = max(Decimal('10.00'), min(score, Decimal('100.00')))
    is_recommended = final_score >= Decimal('70.00')

    return {
        'credit_score': final_score,
        'has_certificate': has_cert,
        'is_recommended': is_recommended,
        'factors': factors
    }


def calculate_multi_season_credit_score(farmer: Farmer) -> CreditScoreSnapshot:
    """
    Computes a multi-season credit score (0-100) using dynamic weights from SystemParameter:
    - Repayment Track Record (default 35%)
    - Production & Biometric Discipline (default 25%)
    - DFAC Training & Certification (default 15%)
    - Field Inspection & Biosecurity Compliance (default 15%)
    - Farm Identity & Geospatial Stability (default 10%)
    """
    # 0. Load dynamic weights from SystemParameter
    w_repay = Decimal(str(SystemParameter.get('CREDIT_WEIGHT_REPAYMENT', default=0.35)))
    w_bio = Decimal(str(SystemParameter.get('CREDIT_WEIGHT_BIOMETRICS', default=0.25)))
    w_cert = Decimal(str(SystemParameter.get('CREDIT_WEIGHT_CERTIFICATION', default=0.15)))
    w_insp = Decimal(str(SystemParameter.get('CREDIT_WEIGHT_INSPECTION', default=0.15)))
    w_stab = Decimal(str(SystemParameter.get('CREDIT_WEIGHT_STABILITY', default=0.10)))
    max_facility = Decimal(str(SystemParameter.get('CREDIT_MAX_FACILITY_LIMIT', default=1500000.00)))

    breakdown = {}

    # Pillar 1: Repayment Performance (0-100)
    past_loans = LoanRecord.objects.filter(farmer=farmer).exclude(status=LoanStatus.APPLIED)
    if past_loans.exists():
        total_principal = sum(l.principal_amount_naira for l in past_loans)
        total_repaid = sum(l.total_repaid_naira for l in past_loans)
        active_arrears = past_loans.filter(status=LoanStatus.DELINQUENT).exists()
        repay_ratio = (total_repaid / total_principal) if total_principal > 0 else Decimal('1.00')
        repay_score = min(Decimal('100.00'), repay_ratio * Decimal('100.00'))
        if active_arrears:
            repay_score = max(Decimal('20.00'), repay_score - Decimal('30.00'))
        breakdown['repayment'] = f"{past_loans.count()} facility/facilities, Repayment ratio: {float(repay_ratio):.1%}"
    else:
        # First-time borrower benchmark
        repay_score = Decimal('70.00')
        breakdown['repayment'] = "First-time borrower baseline (no past default history)"

    # Pillar 2: Biometric & Production Discipline (0-100)
    cycles = ProductionCycle.objects.filter(farm__farmer=farmer)
    logs_count = ProductionLog.objects.filter(cycle__in=cycles).count()
    if logs_count >= 10:
        bio_score = Decimal('95.00')
        breakdown['biometrics'] = f"Exemplary logging discipline ({logs_count} entries recorded)"
    elif logs_count >= 3:
        bio_score = Decimal('75.00')
        breakdown['biometrics'] = f"Satisfactory logging discipline ({logs_count} entries recorded)"
    elif cycles.exists():
        bio_score = Decimal('55.00')
        breakdown['biometrics'] = f"Minimal biometric logging ({logs_count} entries recorded)"
    else:
        bio_score = Decimal('50.00')
        breakdown['biometrics'] = "No historical production cycles logged"

    # Pillar 3: DFAC Training & Certification (0-100)
    valid_certs = Certificate.objects.filter(farmer=farmer, is_valid=True)
    if valid_certs.exists():
        cert_score = Decimal('100.00')
        cert_names = list(valid_certs.values_list('programme__title', flat=True))
        breakdown['certification'] = f"Accredited DFAC certificate held: {', '.join(cert_names)}"
    else:
        cert_score = Decimal('40.00')
        breakdown['certification'] = "No valid DFAC GAP certificate on file"

    # Pillar 4: Field Inspection Compliance (0-100)
    inspections = Inspection.objects.filter(visit__farm__farmer=farmer)
    if inspections.exists():
        compliant_count = inspections.filter(compliance_rating=ComplianceRating.COMPLIANT).count()
        ratio = Decimal(compliant_count) / Decimal(inspections.count())
        insp_score = Decimal('50.00') + (ratio * Decimal('50.00'))
        breakdown['inspection'] = f"{inspections.count()} inspections, {compliant_count} fully compliant"
    else:
        insp_score = Decimal('65.00')
        breakdown['inspection'] = "Baseline uninspected rating"

    # Pillar 5: Farm Stability & Identity (0-100)
    farms = Farm.objects.filter(farmer=farmer)
    if farms.exists():
        has_coords = farms.filter(latitude__isnull=False, longitude__isnull=False).exists()
        stab_score = Decimal('90.00') if has_coords else Decimal('70.00')
        breakdown['stability'] = f"{farms.count()} registered farm location(s) with georeferenced coordinates"
    else:
        stab_score = Decimal('50.00')
        breakdown['stability'] = "No farm facility linked"

    # Risk Flags penalty
    active_risks = RiskFlag.objects.filter(farmer=farmer, is_resolved=False).count()
    risk_deduction = Decimal(min(active_risks * 10, 25))
    if active_risks > 0:
        breakdown['risk_flags'] = f"-{risk_deduction} penalty for {active_risks} unresolved risk flags"

    weighted_score = (
        (repay_score * w_repay) +
        (bio_score * w_bio) +
        (cert_score * w_cert) +
        (insp_score * w_insp) +
        (stab_score * w_stab)
    ) - risk_deduction

    final_score = int(max(Decimal('10.00'), min(weighted_score, Decimal('100.00'))))

    # Determine Rating Tier & Recommended Credit Limit
    if final_score >= 80:
        tier = CreditRatingTier.EXCELLENT
        limit = max_facility
    elif final_score >= 65:
        tier = CreditRatingTier.GOOD
        limit = max_facility * Decimal('0.75')
    elif final_score >= 50:
        tier = CreditRatingTier.MODERATE
        limit = max_facility * Decimal('0.40')
    else:
        tier = CreditRatingTier.HIGH_RISK
        limit = Decimal('0.00')

    snapshot = CreditScoreSnapshot.objects.create(
        farmer=farmer,
        score=final_score,
        rating_tier=tier,
        repayment_score=repay_score,
        biometric_score=bio_score,
        certification_score=cert_score,
        inspection_score=insp_score,
        stability_score=stab_score,
        recommended_credit_limit_naira=limit,
        explanation_breakdown=breakdown,
        assessed_date=timezone.localdate()
    )

    log_audit_event(
        action='CALCULATE_CREDIT_SCORE',
        resource_type='CreditScoreSnapshot',
        resource_id=str(snapshot.id),
        details={
            'farmer_id': str(farmer.id),
            'score': final_score,
            'tier': tier,
            'limit': float(limit)
        }
    )

    return snapshot



@transaction.atomic
def disburse_loan_facility(loan: LoanRecord, disbursed_by=None) -> LoanRecord:
    """Activates credit facility, disburses initial tranche, and generates repayment schedule."""
    if loan.status not in [LoanStatus.APPLIED, LoanStatus.APPROVED]:
        raise ValidationError(f"Cannot disburse loan in status '{loan.get_status_display()}'.")

    today = timezone.now().date()
    loan.status = LoanStatus.DISBURSED
    loan.approval_date = loan.approval_date or today
    loan.disbursement_date = today
    loan.repayment_due_date = today + timedelta(days=loan.tenure_months * 30)
    loan.save()

    # Create monthly repayment schedules
    total_payable = loan.total_payable_naira
    monthly_installment = round(total_payable / Decimal(loan.tenure_months), 2)

    # Clean existing schedules if any
    loan.repayment_schedules.all().delete()
    for month_idx in range(1, loan.tenure_months + 1):
        due = today + timedelta(days=month_idx * 30)
        RepaymentSchedule.objects.create(
            loan=loan,
            installment_number=month_idx,
            due_date=due,
            expected_amount_naira=monthly_installment,
            status=ScheduleStatus.PENDING
        )

    log_audit_event(
        action='DISBURSE_LOAN',
        resource_type='LoanRecord',
        resource_id=str(loan.id),
        user=disbursed_by,
        details={
            'principal_naira': float(loan.principal_amount_naira),
            'total_payable': float(total_payable),
            'farmer': loan.farmer.full_name,
            'lender': loan.lender.institution_name,
            'tenure_months': loan.tenure_months
        }
    )

    return loan


@transaction.atomic
def release_tranche_gate(tranche: LoanTranche, released_by=None, bypass_gate: bool = False) -> LoanTranche:
    """
    Enforces Rule-08: Staged Input Order & Milestone Delivery Gate.
    Tranche N+1 cannot be released unless previous tranche N was fulfilled without dispute.
    """
    loan = tranche.loan

    if tranche.tranche_number > 1 and not bypass_gate:
        previous_tranche = loan.tranches.filter(tranche_number=tranche.tranche_number - 1).first()
        if previous_tranche and previous_tranche.status != TrancheStatus.DISBURSED:
            tranche.status = TrancheStatus.BLOCKED
            tranche.save()
            raise ValidationError(
                f"RULE-08 Compliance Gate: Tranche #{tranche.tranche_number} is blocked. "
                f"Previous Tranche #{previous_tranche.tranche_number} status is '{previous_tranche.get_status_display()}', "
                f"requiring on-farm input delivery confirmation before release."
            )

    tranche.status = TrancheStatus.DISBURSED
    tranche.disbursement_date = timezone.now().date()
    tranche.save()

    log_audit_event(
        action='RELEASE_TRANCHE',
        resource_type='LoanTranche',
        resource_id=str(tranche.id),
        user=released_by,
        details={
            'loan_code': loan.reference_code,
            'tranche_number': tranche.tranche_number,
            'amount_naira': float(tranche.amount_naira),
            'type': tranche.tranche_type
        }
    )

    return tranche


@transaction.atomic
def record_repayment_transaction(
    loan: LoanRecord,
    amount_naira: Decimal,
    payment_method: str = PaymentMethod.BANK_TRANSFER,
    transaction_reference: Optional[str] = None,
    schedule: Optional[RepaymentSchedule] = None,
    notes: str = "",
    recorded_by=None
) -> Repayment:
    """Records an incoming loan remittance, updates schedules, and recalculates loan status."""
    if not transaction_reference:
        transaction_reference = f"TXN-DFAC-{uuid.uuid4().hex[:10].upper()}"

    repayment = Repayment.objects.create(
        loan=loan,
        schedule=schedule,
        amount_naira=amount_naira,
        payment_date=timezone.now().date(),
        payment_method=payment_method,
        transaction_reference=transaction_reference,
        notes=notes,
        recorded_by=recorded_by
    )

    # Increment loan total repaid
    loan.total_repaid_naira += amount_naira
    if loan.total_repaid_naira >= loan.total_payable_naira:
        loan.status = LoanStatus.REPAID
        # Clear arrears flags
        loan.risk_flags.filter(rule_triggered='RULE-02', is_resolved=False).update(
            is_resolved=True,
            resolved_at=timezone.now(),
            resolved_by=recorded_by
        )
    elif loan.status == LoanStatus.DELINQUENT:
        loan.status = LoanStatus.PERFORMING
    loan.save()

    # Credit schedules in chronological order
    remaining_credit = amount_naira
    pending_schedules = loan.repayment_schedules.filter(
        status__in=[ScheduleStatus.PENDING, ScheduleStatus.PARTIALLY_PAID, ScheduleStatus.OVERDUE]
    ).order_by('due_date')

    for sch in pending_schedules:
        needed = sch.expected_amount_naira - sch.paid_amount_naira
        if remaining_credit >= needed:
            sch.paid_amount_naira = sch.expected_amount_naira
            sch.status = ScheduleStatus.PAID
            sch.paid_date = timezone.now().date()
            sch.save()
            remaining_credit -= needed
        else:
            sch.paid_amount_naira += remaining_credit
            sch.status = ScheduleStatus.PARTIALLY_PAID
            sch.save()
            remaining_credit = Decimal('0.00')
            break

    log_audit_event(
        action='RECORD_REPAYMENT',
        resource_type='Repayment',
        resource_id=str(repayment.id),
        user=recorded_by,
        details={
            'loan_code': loan.reference_code,
            'amount_naira': float(amount_naira),
            'method': payment_method,
            'new_balance': float(loan.outstanding_balance_naira)
        }
    )

    return repayment
