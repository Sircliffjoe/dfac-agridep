import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError

from agridep.apps.registry.models import Farmer, Farm, Buyer, VerificationStatus
from agridep.apps.production.models import ProductionCycle, ProduceBatch, ProduceBatchStatus, ProduceQualityGrade, CycleStage
from agridep.apps.finance.models import (
    Lender,
    LenderType,
    LoanRecord,
    LoanStatus,
    LoanTranche,
    TrancheType,
    TrancheStatus,
    RepaymentSchedule,
    ScheduleStatus,
    Repayment,
    RiskFlag,
    RiskSeverity,
)
from agridep.apps.finance.services import (
    calculate_loan_expected_value_and_risk,
    evaluate_loan_credit_score,
    release_tranche_gate,
    record_repayment_transaction,
    disburse_loan_facility,
)
from agridep.apps.market.models import (
    BuyerDemand,
    DemandStatus,
    ProduceMatch,
    MatchStatus,
    OfftakeTransaction,
    CommodityPrice,
)
from agridep.apps.market.services import (
    find_matching_produce_for_demand,
    propose_buyer_matches_for_demand,
    confirm_produce_match,
)
from agridep.apps.training.models import TrainingProgramme, TrainingSession, Certificate


@pytest.fixture
def lender_inst(db, admin_user):
    return Lender.objects.create(
        institution_name="Test Delta Agricultural Microfinance",
        institution_type=LenderType.MICROFINANCE_BANK,
        contact_person="Mrs. Credit Officer",
        phone="+2348031110001",
        concessionary_rate_pct=Decimal('9.00')
    )


@pytest.fixture
def test_farmer(db, delta_cohort, officer_user):
    farmer = Farmer.objects.create(
        first_name="Godspower",
        last_name="Omene",
        gender="MALE",
        state="Delta",
        lga="Warri South",
        community_address="Osubi Community",
        cohort=delta_cohort,
        assigned_officer=officer_user,
        phone_normalized="+2348032223344",
        verification_status=VerificationStatus.VERIFIED
    )
    farmer.set_nin("98765432101")
    farmer.save()
    return farmer


@pytest.fixture
def test_farm_and_cycle(db, test_farmer, catfish_enterprise):
    farm = Farm.objects.create(
        farmer=test_farmer,
        name="Omene Catfish Farm",
        latitude=Decimal('5.545000'),
        longitude=Decimal('5.762000'),
        number_of_ponds=6,
        total_area_hectares=Decimal('0.85'),
        water_source='BOREHOLE'
    )
    farm.enterprise_types.add(catfish_enterprise)

    cycle = ProductionCycle.objects.create(
        farm=farm,
        enterprise_type=catfish_enterprise,
        cycle_name="Omene Main Pond 1 Cycle",
        start_date=date.today() - timedelta(days=120),
        projected_harvest_date=date.today() + timedelta(days=15),
        initial_stock_count=2000,
        current_stock_count=1900,
        initial_average_weight_g=Decimal('10.0'),
        current_average_weight_g=Decimal('850.0'),
        status=CycleStage.GROWING
    )

    batch = ProduceBatch.objects.create(
        cycle=cycle,
        farm=farm,
        produce_type=catfish_enterprise,
        projected_volume_kg=Decimal('1000.00'),  # 1,000 kg @ ₦2,500 = ₦2,500,000 harvest value
        projected_harvest_window_start=date.today() + timedelta(days=10),
        projected_harvest_window_end=date.today() + timedelta(days=20),
        quality_grade=ProduceQualityGrade.GRADE_A,
        status=ProduceBatchStatus.AVAILABLE
    )

    return farm, cycle, batch


@pytest.mark.django_db
def test_loan_expected_value_and_risk_coverage_model(lender_inst, test_farmer, test_farm_and_cycle):
    """
    Framework Benchmark: ₦200,000 loan against expected harvest (₦850,000+).
    Asserts normal healthy operating coverage ratio >= 2.50x.
    """
    farm, cycle, batch = test_farm_and_cycle

    # ₦200,000 principal at 9% interest -> Total payable = ₦218,000
    loan = LoanRecord.objects.create(
        farmer=test_farmer,
        lender=lender_inst,
        farm=farm,
        production_cycle=cycle,
        principal_amount_naira=Decimal('200000.00'),
        interest_rate_percent=Decimal('9.00'),
        tenure_months=6,
        status=LoanStatus.DISBURSED,
        disbursement_date=date.today() - timedelta(days=30)
    )

    analysis = calculate_loan_expected_value_and_risk(loan)
    
    # 1,000kg * ₦2,500 = ₦2,500,000 expected harvest
    # Coverage = ₦2,500,000 / ₦218,000 ~ 11.47x (>= 2.50x)
    assert analysis['coverage_ratio'] >= Decimal('2.50')
    assert analysis['risk_level'] == 'LOW'
    assert len(analysis['flags_raised']) == 0


@pytest.mark.django_db
def test_rule_03_yield_deficit_coverage_breach(lender_inst, test_farmer, test_farm_and_cycle):
    """
    RULE-03: When projected harvest drops significantly, coverage ratio drops below 1.20x,
    raising a CRITICAL risk flag and transitioning loan to WATCHLIST.
    """
    farm, cycle, batch = test_farm_and_cycle

    # Reduce batch projected volume to 80kg (80kg * ₦2,500 = ₦200,000) against a ₦200,000 loan (payable ₦218,000)
    # Ratio = 200,000 / 218,000 = 0.92 < 1.20x
    batch.projected_volume_kg = Decimal('80.00')
    batch.save()
    cycle.current_stock_count = 100
    cycle.current_average_weight_g = Decimal('800.0')
    cycle.save()

    loan = LoanRecord.objects.create(
        farmer=test_farmer,
        lender=lender_inst,
        farm=farm,
        production_cycle=cycle,
        principal_amount_naira=Decimal('200000.00'),
        interest_rate_percent=Decimal('9.00'),
        tenure_months=6,
        status=LoanStatus.DISBURSED,
        disbursement_date=date.today() - timedelta(days=30)
    )

    analysis = calculate_loan_expected_value_and_risk(loan)
    assert analysis['coverage_ratio'] < Decimal('1.20')
    assert analysis['risk_level'] == 'CRITICAL'
    assert RiskFlag.objects.filter(loan=loan, rule_triggered='RULE-03', severity=RiskSeverity.CRITICAL).exists()
    
    loan.refresh_from_db()
    assert loan.status == LoanStatus.WATCHLIST


@pytest.mark.django_db
def test_rule_02_repayment_arrears_detection_and_resolution(lender_inst, test_farmer, test_farm_and_cycle):
    """
    RULE-02: Overdue installment (> 7 days past due date) raises HIGH risk flag
    and transitions loan to DELINQUENT. Full repayment clears delinquency.
    """
    farm, cycle, batch = test_farm_and_cycle

    loan = LoanRecord.objects.create(
        farmer=test_farmer,
        lender=lender_inst,
        farm=farm,
        production_cycle=cycle,
        principal_amount_naira=Decimal('100000.00'),
        interest_rate_percent=Decimal('9.00'),
        tenure_months=3,
        status=LoanStatus.DISBURSED,
        disbursement_date=date.today() - timedelta(days=60)
    )

    # Overdue schedule 10 days ago
    sch = RepaymentSchedule.objects.create(
        loan=loan,
        installment_number=1,
        due_date=date.today() - timedelta(days=10),
        expected_amount_naira=Decimal('36333.33'),
        status=ScheduleStatus.PENDING
    )

    # Trigger risk evaluation
    analysis = calculate_loan_expected_value_and_risk(loan)
    loan.refresh_from_db()
    sch.refresh_from_db()

    assert loan.status == LoanStatus.DELINQUENT
    assert sch.status == ScheduleStatus.OVERDUE
    assert RiskFlag.objects.filter(loan=loan, rule_triggered='RULE-02', severity=RiskSeverity.HIGH).exists()

    # Make full repayment
    record_repayment_transaction(
        loan=loan,
        amount_naira=loan.total_payable_naira,
        transaction_reference="TXN-SETTLE-FULL-001"
    )

    loan.refresh_from_db()
    assert loan.status == LoanStatus.REPAID
    assert loan.outstanding_balance_naira == Decimal('0.00')


@pytest.mark.django_db
def test_rule_05_transparent_credit_scoring_with_certification_bonus(test_farmer, catfish_enterprise):
    """
    RULE-05: Holding an accredited, valid Certificate in target enterprise type adds +15 bonus points.
    """
    # 1. Without certificate
    score_before = evaluate_loan_credit_score(test_farmer, catfish_enterprise)
    # Base 65.0 + verified smallholder 10.0 = 75.0
    assert score_before['has_certificate'] is False
    assert score_before['credit_score'] == Decimal('75.00')

    # 2. Issue accredited certificate
    prog = TrainingProgramme.objects.create(
        title="Aquaculture Nursery Mastery",
        enterprise_type=catfish_enterprise,
        duration_days=5
    )
    sess = TrainingSession.objects.create(
        programme=prog,
        venue="Warri Demonstration",
        start_date=date.today() - timedelta(days=20),
        end_date=date.today() - timedelta(days=15)
    )
    Certificate.objects.create(
        farmer=test_farmer,
        programme=prog,
        session=sess,
        is_valid=True
    )

    score_after = evaluate_loan_credit_score(test_farmer, catfish_enterprise)
    assert score_after['has_certificate'] is True
    # 75.0 + 15.0 = 90.0
    assert score_after['credit_score'] == Decimal('90.00')


@pytest.mark.django_db
def test_rule_08_input_order_tranche_gate(lender_inst, test_farmer):
    """
    RULE-08: Staged input delivery gate. Releasing Tranche N+1 before Tranche N is disbursed is blocked.
    """
    loan = LoanRecord.objects.create(
        farmer=test_farmer,
        lender=lender_inst,
        principal_amount_naira=Decimal('300000.00'),
        status=LoanStatus.DISBURSED
    )
    t1 = LoanTranche.objects.create(
        loan=loan,
        tranche_number=1,
        amount_naira=Decimal('180000.00'),
        tranche_type=TrancheType.IN_KIND_INPUTS,
        status=TrancheStatus.PENDING_APPROVAL,
        milestone_conditions="5,000 fingerlings delivery confirmed"
    )
    t2 = LoanTranche.objects.create(
        loan=loan,
        tranche_number=2,
        amount_naira=Decimal('120000.00'),
        tranche_type=TrancheType.CASH_WORKING_CAPITAL,
        status=TrancheStatus.PENDING_APPROVAL,
        milestone_conditions="Month 2 pond labor and water conditioning"
    )

    # Attempting to release Tranche 2 while Tranche 1 is pending approval must raise ValidationError
    with pytest.raises(ValidationError) as exc:
        release_tranche_gate(t2)
    assert "RULE-08 Compliance Gate" in str(exc.value)

    # Release Tranche 1 first
    release_tranche_gate(t1)
    t1.refresh_from_db()
    assert t1.status == TrancheStatus.DISBURSED

    # Now Tranche 2 release succeeds
    release_tranche_gate(t2)
    t2.refresh_from_db()
    assert t2.status == TrancheStatus.DISBURSED


@pytest.mark.django_db
def test_rule_04_buyer_demand_matching_and_offtake_confirmation(buyer_user, catfish_enterprise, test_farm_and_cycle):
    """
    RULE-04: Solves "Buyer needs X tonnes in Delta State by Month Y".
    Matches candidate batch, confirms contract, generates OfftakeTransaction with waybill.
    """
    farm, cycle, batch = test_farm_and_cycle
    buyer = buyer_user.buyer_profile

    # Buyer logs demand for 800 kg @ ₦2,600/kg in Warri South
    demand = BuyerDemand.objects.create(
        buyer=buyer,
        enterprise_type=catfish_enterprise,
        target_volume_kg=Decimal('800.00'),
        offered_price_per_kg_naira=Decimal('2600.00'),
        minimum_grade=ProduceQualityGrade.GRADE_A,
        target_delivery_window_start=batch.projected_harvest_window_start,
        target_delivery_window_end=batch.projected_harvest_window_end,
        delivery_latitude=Decimal('5.520000'),
        delivery_longitude=Decimal('5.750000'),
        max_delivery_radius_km=50
    )

    # 1. Run matching algorithm
    matches = propose_buyer_matches_for_demand(demand)
    assert len(matches) == 1
    match = matches[0]
    assert match.allocated_volume_kg == Decimal('800.00')
    assert match.status == MatchStatus.PROPOSED
    assert demand.status == DemandStatus.FULLY_MATCHED

    # 2. Confirm contract
    offtake = confirm_produce_match(match, confirmed_by=buyer_user)
    assert offtake.waybill_number.startswith('DFAC-WB-')
    assert offtake.actual_delivered_volume_kg == Decimal('800.00')
    assert offtake.total_amount_naira == Decimal('800.00') * Decimal('2600.00')
    
    match.refresh_from_db()
    batch.refresh_from_db()
    assert match.status == MatchStatus.CONTRACTED
    assert batch.status == ProduceBatchStatus.MATCHED


@pytest.mark.django_db
def test_rbac_buyer_denied_financial_loans(api_client, buyer_user, lender_inst, test_farmer):
    """
    RBAC Matrix: Commercial buyer is strictly DENIED access to financial loan records.
    Querying /api/v1/finance/loans/ returns an empty queryset (no cross-tenant leakage).
    """
    # Create a loan
    LoanRecord.objects.create(
        farmer=test_farmer,
        lender=lender_inst,
        principal_amount_naira=Decimal('250000.00'),
        status=LoanStatus.DISBURSED
    )

    api_client.force_authenticate(user=buyer_user)
    res = api_client.get('/api/v1/finance/loans/')
    assert res.status_code == 200
    assert len(res.json().get('results', res.json())) == 0
