import io
import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
import openpyxl

from agridep.apps.registry.models import Farmer, Farm, EnterpriseType, Buyer
from agridep.apps.finance.models import (
    Lender,
    LoanRecord,
    LoanStatus,
    LoanTranche,
    TrancheType,
    TrancheStatus,
    CreditRatingTier,
    CreditScoreSnapshot,
)
from agridep.apps.finance.services import calculate_multi_season_credit_score
from agridep.apps.production.models import ProductionCycle, ProduceBatch, ProduceBatchStatus, ProductionLog
from agridep.apps.inputs.models import (
    InputSupplier,
    SupplierCategory,
    InputCatalogItem,
    InputOrder,
    OrderStatus,
    DeliveryConfirmationChannel,
)
from agridep.apps.inputs.services import (
    create_input_order,
    dispatch_input_order,
    confirm_input_delivery,
    verify_tranche_input_delivery_gate,
)
from agridep.apps.market.models import BuyerDemand, ProduceMatch, CommodityPrice
from agridep.apps.market.services import (
    calculate_regional_price_index,
    analyze_supply_demand_gap,
    get_recommended_farmgate_price,
)
from agridep.apps.reporting.services import (
    compute_donor_me_indicators,
    generate_donor_excel_report,
    generate_donor_pdf_report,
)
from agridep.apps.common.models import SystemParameter


@pytest.fixture
def api_client(admin_user):
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client


@pytest.fixture
def m7_test_data(db, admin_user):
    """Sets up a complete ecosystem for Milestone M7 testing."""
    catfish, _ = EnterpriseType.objects.get_or_create(
        name="African Catfish",
        defaults={"category": "AQUACULTURE"}
    )
    farmer = Farmer.objects.create(
        first_name="Preye",
        last_name="Boma",
        gender="FEMALE",
        phone_normalized="+2348037776655",
        state="Delta",
        lga="Warri South",
        dob=timezone.localdate() - timedelta(days=28 * 365)  # 28 years old (Youth)
    )
    farm = Farm.objects.create(
        farmer=farmer,
        name="Preye Aquaculture Ponds",
        latitude=Decimal("5.522000"),
        longitude=Decimal("5.749000")
    )
    farm.enterprise_types.add(catfish)

    cycle = ProductionCycle.objects.create(
        farm=farm,
        enterprise_type=catfish,
        cycle_name="Cycle 2026-Test",
        start_date=timezone.localdate() - timedelta(days=60),
        projected_harvest_date=timezone.localdate() + timedelta(days=30),
        initial_stock_count=3000,
        current_stock_count=2900,
        status="STOCKED"
    )

    lender = Lender.objects.create(
        institution_name="Delta Agro Credit Bank",
        institution_type="COMMERCIAL_BANK",
        contact_person="Austin Briggs",
        phone="+2348031234567"
    )

    loan = LoanRecord.objects.create(
        farmer=farmer,
        lender=lender,
        farm=farm,
        principal_amount_naira=Decimal('300000.00'),
        interest_rate_percent=Decimal('9.00'),
        tenure_months=6,
        status=LoanStatus.DISBURSED
    )

    tranche1 = LoanTranche.objects.create(
        loan=loan,
        tranche_number=1,
        amount_naira=Decimal('150000.00'),
        tranche_type=TrancheType.IN_KIND_INPUTS,
        status=TrancheStatus.DISBURSED
    )

    tranche2 = LoanTranche.objects.create(
        loan=loan,
        tranche_number=2,
        amount_naira=Decimal('150000.00'),
        tranche_type=TrancheType.IN_KIND_INPUTS,
        status=TrancheStatus.PENDING_APPROVAL
    )

    supplier = InputSupplier.objects.create(
        supplier_name="Warri Fish Feed & Fingerling Depot",
        category=SupplierCategory.AQUACULTURE_FEED,
        contact_name="Chief Diri",
        phone="+2348039998877",
        state="Delta",
        lga="Warri South",
        warehouse_address="45 NPA Expressway, Warri",
        is_verified=True,
        rating=Decimal('4.75')
    )

    item1 = InputCatalogItem.objects.create(
        supplier=supplier,
        enterprise_type=catfish,
        item_name="Skretting 2mm Starter Feed (25kg)",
        item_code="TEST-SKRET-2MM",
        unit_of_measure="25kg Bag",
        unit_price_naira=Decimal('35000.00'),
        in_stock=True
    )

    return farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish


@pytest.mark.django_db
def test_input_supplier_directory_and_catalog(m7_test_data):
    """Verifies input supplier registry and product catalog specifications."""
    farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish = m7_test_data

    assert supplier.is_verified is True
    assert supplier.rating >= Decimal('4.00')
    assert supplier.catalog_items.count() == 1
    assert item1.unit_price_naira == Decimal('35000.00')


@pytest.mark.django_db
def test_input_order_creation_and_delivery_confirmation(m7_test_data):
    """Verifies creation of in-kind input order and on-farm delivery confirmation."""
    farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish = m7_test_data

    order = create_input_order(
        farmer=farmer,
        farm=farm,
        supplier=supplier,
        items=[{'catalog_item': item1, 'quantity': Decimal('4')}],
        loan=loan,
        tranche=tranche1
    )

    assert order.status == OrderStatus.SUBMITTED
    assert order.total_amount_naira == Decimal('140000.00')  # 4 x 35,000
    assert order.tranche == tranche1

    # Dispatch
    dispatched = dispatch_input_order(order, waybill_number="WB-DEL-0091")
    assert dispatched.status == OrderStatus.DISPATCHED
    assert dispatched.waybill_number == "WB-DEL-0091"

    # Confirm delivery
    confirmed = confirm_input_delivery(
        order=dispatched,
        confirmation_channel=DeliveryConfirmationChannel.FIELD_OFFICER_INSPECTION,
        notes="All 4 bags intact."
    )
    assert confirmed.status == OrderStatus.DELIVERED_CONFIRMED
    assert confirmed.delivered_at is not None


@pytest.mark.django_db
def test_rule_08_input_order_delivery_tranche_gate(m7_test_data):
    """
    Enforces Rule-08: Staged Input Order & Milestone Delivery Gate.
    Tranche #2 cannot proceed until Tranche #1 input delivery is confirmed.
    """
    farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish = m7_test_data

    # Create unconfirmed order linked to Tranche 1
    order = create_input_order(
        farmer=farmer,
        farm=farm,
        supplier=supplier,
        items=[{'catalog_item': item1, 'quantity': Decimal('2')}],
        loan=loan,
        tranche=tranche1
    )

    # Check Tranche 2 gate: should be BLOCKED because order is not delivered
    gate_check = verify_tranche_input_delivery_gate(tranche2)
    assert gate_check['allowed'] is False
    assert "unconfirmed input orders" in gate_check['reason']
    assert order.order_code in gate_check['blocked_by_orders']

    # Now confirm delivery
    confirm_input_delivery(order, confirmation_channel=DeliveryConfirmationChannel.PORTAL_MANUAL)

    # Re-verify gate: should now be allowed
    gate_check_after = verify_tranche_input_delivery_gate(tranche2)
    assert gate_check_after['allowed'] is True


@pytest.mark.django_db
def test_multi_season_credit_scoring_engine(m7_test_data):
    """Verifies transparent multi-season credit scoring with dynamic system weights."""
    farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish = m7_test_data

    # Farmer has completed full repayment on past facility
    loan.total_repaid_naira = Decimal('300000.00')
    loan.save(update_fields=['total_repaid_naira'])

    # Add some production logs to build biometric discipline
    for i in range(5):
        ProductionLog.objects.create(
            cycle=cycle,
            log_date=timezone.localdate() - timedelta(days=i * 7),
            sampling_average_weight_g=Decimal('350.00'),
            observed_mortality_count=2,
            feed_consumed_kg=Decimal('25.00')
        )

    snapshot = calculate_multi_season_credit_score(farmer)

    assert snapshot is not None
    assert 0 <= snapshot.score <= 100
    assert snapshot.rating_tier in [CreditRatingTier.EXCELLENT, CreditRatingTier.GOOD, CreditRatingTier.MODERATE]
    assert snapshot.recommended_credit_limit_naira > Decimal('0.00')
    assert 'repayment' in snapshot.explanation_breakdown
    assert 'biometrics' in snapshot.explanation_breakdown


@pytest.mark.django_db
def test_market_price_index_and_supply_demand_gap(m7_test_data):
    """Tests regional market price index aggregation and supply-demand gap analysis."""
    farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish = m7_test_data

    # Seed commodity prices
    CommodityPrice.objects.create(
        enterprise_type=catfish,
        market_hub="Effurun Central Market, Warri",
        state="Delta",
        price_per_kg_naira=Decimal('2650.00'),
        effective_date=timezone.localdate()
    )
    CommodityPrice.objects.create(
        enterprise_type=catfish,
        market_hub="Sapele Modern Fish Market",
        state="Delta",
        price_per_kg_naira=Decimal('2550.00'),
        effective_date=timezone.localdate()
    )

    index = calculate_regional_price_index(enterprise_type=catfish, state="Delta")
    assert index['average_price_per_kg_naira'] == Decimal('2600.00')
    assert index['sample_count'] == 2

    # Create produce batch (supply) and buyer demand (demand)
    batch = ProduceBatch.objects.create(
        farm=farm,
        cycle=cycle,
        produce_type=catfish,
        projected_volume_kg=Decimal('4000.00'),
        projected_harvest_window_start=timezone.localdate() + timedelta(days=10),
        projected_harvest_window_end=timezone.localdate() + timedelta(days=20),
        status=ProduceBatchStatus.AVAILABLE
    )

    rec_price = get_recommended_farmgate_price(batch)
    assert rec_price >= Decimal('2500.00')

    buyer = Buyer.objects.create(
        company_name="Delta Seafood Processors",
        contact_name="Chief Ebi",
        phone="+2348039990000"
    )
    demand = BuyerDemand.objects.create(
        buyer=buyer,
        enterprise_type=catfish,
        target_volume_kg=Decimal('6000.00'),
        offered_price_per_kg_naira=Decimal('2600.00'),
        target_delivery_window_start=timezone.localdate() + timedelta(days=5),
        target_delivery_window_end=timezone.localdate() + timedelta(days=25)
    )

    gap = analyze_supply_demand_gap(enterprise_type=catfish, state="Delta", window_days=60)
    assert gap['total_upcoming_supply_kg'] == 4000.0
    assert gap['total_active_demand_kg'] == 6000.0
    assert gap['market_condition'] == "SUPPLY_DEFICIT"


@pytest.mark.django_db
def test_donor_me_indicators_computation(m7_test_data):
    """Tests PIND / GIZ M&E indicators aggregation with gender and youth disaggregation."""
    farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish = m7_test_data

    indicators = compute_donor_me_indicators(donor="PIND")

    assert indicators['donor'] == "PIND"
    assert "Foundation for Partnership Initiatives" in indicators['donor_full_name']
    assert indicators['demographics']['total_farmers'] >= 1
    assert indicators['demographics']['female_percentage'] > 0.0
    assert indicators['demographics']['youth_percentage'] > 0.0
    assert indicators['financial_inclusion']['total_principal_mobilized_naira'] >= 300000.0


@pytest.mark.django_db
def test_donor_excel_export_binary(m7_test_data):
    """Tests automated Excel workbook generation (.xlsx) for donor submission."""
    indicators = compute_donor_me_indicators(donor="PIND")
    excel_buf = generate_donor_excel_report(indicators)

    assert excel_buf is not None
    excel_bytes = excel_buf.getvalue()
    assert len(excel_bytes) > 1000

    # Validate that openpyxl can load and read the workbook
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Executive Summary" in wb.sheetnames
    assert "Demographics & Geography" in wb.sheetnames
    ws1 = wb["Executive Summary"]
    assert "DFAC AgriDEP" in str(ws1.cell(1, 1).value)


@pytest.mark.django_db
def test_donor_pdf_export_binary(m7_test_data):
    """Tests automated publication-grade PDF report generation for donors."""
    indicators = compute_donor_me_indicators(donor="PIND")
    pdf_buf = generate_donor_pdf_report(indicators)

    assert pdf_buf is not None
    pdf_bytes = pdf_buf.getvalue()
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b'%PDF-')


@pytest.mark.django_db
def test_api_reporting_and_inputs_endpoints(api_client, m7_test_data):
    """Verifies REST API endpoints for donor indicators, exports, and input suppliers."""
    farmer, farm, cycle, loan, tranche1, tranche2, supplier, item1, catfish = m7_test_data

    # 1. Donor indicators JSON endpoint
    resp_ind = api_client.get('/api/v1/reporting/indicators/?donor=PIND')
    assert resp_ind.status_code == status.HTTP_200_OK
    assert resp_ind.data['donor'] == 'PIND'

    # 2. Excel export endpoint
    resp_xl = api_client.get('/api/v1/reporting/export/excel/?donor=PIND')
    assert resp_xl.status_code == status.HTTP_200_OK
    assert resp_xl['Content-Type'] == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    assert len(resp_xl.content) > 1000

    # 3. PDF export endpoint
    resp_pdf = api_client.get('/api/v1/reporting/export/pdf/?donor=PIND')
    assert resp_pdf.status_code == status.HTTP_200_OK
    assert resp_pdf['Content-Type'] == 'application/pdf'
    assert resp_pdf.content.startswith(b'%PDF-')

    # 4. Input suppliers endpoint
    resp_sup = api_client.get('/api/v1/inputs/suppliers/')
    assert resp_sup.status_code == status.HTTP_200_OK
    assert len(resp_sup.data) >= 1

    # 5. Smallholder Credit Score endpoint
    resp_cs = api_client.get(f'/api/v1/finance/credit-score/{farmer.id}/')
    assert resp_cs.status_code == status.HTTP_200_OK
    assert 'score' in resp_cs.data
    assert 'rating_tier' in resp_cs.data
