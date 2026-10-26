import pytest
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from agridep.apps.registry.models import Farmer, Farm, EnterpriseType, Buyer
from agridep.apps.finance.models import Lender, LoanRecord, LoanStatus, RepaymentSchedule, ScheduleStatus
from agridep.apps.production.models import ProductionCycle, ProduceBatch, ProduceBatchStatus, ProductionLog
from agridep.apps.market.models import BuyerDemand, ProduceMatch, MatchStatus
from agridep.apps.fieldops.models import VisitAssignment, AssignmentPriority, IncidentReport
from agridep.apps.alerts.models import AlertNotification, AlertStatus, AlertPriority
from agridep.apps.alerts.services import (
    send_transactional_sms,
    notify_harvest_readiness,
    notify_repayment_due,
    notify_emergency_disease,
    notify_buyer_match_proposed,
)


@pytest.fixture
def farmer_with_loan(db, officer_user):
    farmer = Farmer.objects.create(
        first_name="Tari",
        last_name="Agidee",
        phone_normalized="+2348030000011",
        state="Delta",
        lga="Ughelli North",
        assigned_officer=officer_user
    )
    farm = Farm.objects.create(
        farmer=farmer,
        name="Tari's Catfish Farm",
        latitude=Decimal("5.544230"),
        longitude=Decimal("5.760260")
    )
    catfish = EnterpriseType.objects.create(name="African Catfish", category="AQUACULTURE")
    farm.enterprise_types.add(catfish)

    cycle = ProductionCycle.objects.create(
        farm=farm,
        enterprise_type=catfish,
        cycle_name="Cycle 2026",
        start_date=timezone.localdate() - timedelta(days=60),
        projected_harvest_date=timezone.localdate() + timedelta(days=30),
        initial_stock_count=4000,
        current_stock_count=3800
    )

    lender = Lender.objects.create(
        institution_name="Bank of Agriculture (BOA)",
        contact_person="Director Aliu",
        email="boa@dfac.ng",
        phone="+2348030009999"
    )

    loan = LoanRecord.objects.create(
        farmer=farmer,
        lender=lender,
        farm=farm,
        principal_amount_naira=Decimal('200000.00'),
        interest_rate_percent=Decimal('9.00'),
        tenure_months=6,
        status=LoanStatus.DISBURSED
    )
    RepaymentSchedule.objects.create(
        loan=loan,
        installment_number=1,
        due_date=timezone.localdate() + timedelta(days=14),
        expected_amount_naira=Decimal('40000.00'),
        status=ScheduleStatus.PENDING
    )
    return farmer, farm, loan, cycle


@pytest.mark.django_db
def test_africas_talking_mock_adapter_sms_dispatch():
    """Verifies that transactional SMS messages dispatch and record audit notifications."""
    phone = "+2348039998877"
    msg = "DFAC AgriDEP: Your catfish batch is harvest-ready. Dial *384*223# to review buyer offers."

    notif = send_transactional_sms(phone, msg, priority=AlertPriority.HIGH)
    assert notif is not None
    assert notif.status == AlertStatus.SENT
    assert notif.recipient_phone == phone
    assert "AT_MOCK_" in notif.provider_reference


@pytest.mark.django_db
def test_ussd_main_menu(api_client, farmer_with_loan):
    """Verifies that dialing *384*223# returns the main personalized smallholder menu."""
    farmer, farm, loan, cycle = farmer_with_loan

    payload = {
        "sessionId": "AT_SESSION_001",
        "phoneNumber": farmer.phone_normalized,
        "text": "",
        "networkCode": "MTN_NG"
    }

    resp = api_client.post('/api/v1/alerts/ussd/', data=payload, format='json')
    assert resp.status_code == status.HTTP_200_OK
    text = resp.content.decode('utf-8')
    assert text.startswith("CON ")
    assert f"Welcome {farmer.first_name}" in text
    assert "1. Check Loan & Repayment" in text
    assert "2. Report Pond Mortality & Feed" in text


@pytest.mark.django_db
def test_ussd_check_loan_balance(api_client, farmer_with_loan):
    """Option 1: Farmer checks outstanding loan balance and repayment date via USSD."""
    farmer, farm, loan, cycle = farmer_with_loan

    payload = {
        "sessionId": "AT_SESSION_002",
        "phoneNumber": farmer.phone_normalized,
        "text": "1",
        "networkCode": "MTN_NG"
    }

    resp = api_client.post('/api/v1/alerts/ussd/', data=payload, format='json')
    assert resp.status_code == status.HTTP_200_OK
    text = resp.content.decode('utf-8')
    assert text.startswith("END ")
    assert loan.reference_code in text
    assert "Principal: NGN 200,000" in text
    assert "Outstanding: NGN 200,000" in text


@pytest.mark.django_db
def test_ussd_multi_turn_production_logging(api_client, farmer_with_loan):
    """Option 2: Multi-turn prompt for daily mortality and feed consumption."""
    farmer, farm, loan, cycle = farmer_with_loan

    # Turn 1: Select option 2 -> prompt for dead fish
    resp1 = api_client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "AT_SESSION_003",
        "phoneNumber": farmer.phone_normalized,
        "text": "2"
    }, format='json')
    text1 = resp1.content.decode('utf-8')
    assert text1.startswith("CON ")
    assert "Enter observed dead fish count" in text1

    # Turn 2: Enter 15 dead fish -> prompt for feed (kg)
    resp2 = api_client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "AT_SESSION_003",
        "phoneNumber": farmer.phone_normalized,
        "text": "2*15"
    }, format='json')
    text2 = resp2.content.decode('utf-8')
    assert text2.startswith("CON ")
    assert "Enter commercial feed consumed today" in text2

    # Turn 3: Enter 25 kg feed -> commits production log!
    resp3 = api_client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "AT_SESSION_003",
        "phoneNumber": farmer.phone_normalized,
        "text": "2*15*25"
    }, format='json')
    text3 = resp3.content.decode('utf-8')
    assert text3.startswith("END ")
    assert "Logged 15 dead fish and 25.0kg feed" in text3

    # Assert in Database
    log = ProductionLog.objects.filter(cycle=cycle).order_by('-created_at').first()
    assert log is not None
    assert log.observed_mortality_count == 15
    assert log.feed_consumed_kg == Decimal('25.0')


@pytest.mark.django_db
def test_ussd_market_prices(api_client):
    """Option 3: Smallholder retrieves regional market commodity prices."""
    payload = {
        "sessionId": "AT_SESSION_004",
        "phoneNumber": "+2348039999999",
        "text": "3"
    }
    resp = api_client.post('/api/v1/alerts/ussd/', data=payload, format='json')
    assert resp.status_code == status.HTTP_200_OK
    text = resp.content.decode('utf-8')
    assert text.startswith("END ")
    assert "DFAC Niger Delta" in text
    assert "Catfish" in text or "NGN" in text


@pytest.mark.django_db
def test_ussd_buyer_match_confirmation(api_client, farmer_with_loan):
    """Option 4: Farmer reviews and accepts a proposed commercial buyer match."""
    farmer, farm, loan, cycle = farmer_with_loan
    catfish = farm.enterprise_types.first()

    batch = ProduceBatch.objects.create(
        farm=farm,
        cycle=cycle,
        produce_type=catfish,
        projected_volume_kg=Decimal('3000.00'),
        projected_harvest_window_start=timezone.localdate() + timedelta(days=5),
        projected_harvest_window_end=timezone.localdate() + timedelta(days=15),
        status=ProduceBatchStatus.AVAILABLE
    )
    buyer = Buyer.objects.create(
        company_name="Warri Mega Processors Ltd",
        contact_name="Chief Diri",
        phone="+2348031110000"
    )
    demand = BuyerDemand.objects.create(
        buyer=buyer,
        enterprise_type=catfish,
        target_volume_kg=Decimal('5000.00'),
        offered_price_per_kg_naira=Decimal('2600.00'),
        target_delivery_window_start=timezone.localdate() + timedelta(days=5),
        target_delivery_window_end=timezone.localdate() + timedelta(days=25),
    )
    match = ProduceMatch.objects.create(
        buyer_demand=demand,
        produce_batch=batch,
        allocated_volume_kg=Decimal('2500.00'),
        agreed_price_per_kg_naira=Decimal('2600.00'),
        status=MatchStatus.PROPOSED
    )

    # Turn 1: Option 4 -> Prompt offer
    resp1 = api_client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "AT_SESSION_005",
        "phoneNumber": farmer.phone_normalized,
        "text": "4"
    }, format='json')
    text1 = resp1.content.decode('utf-8')
    assert text1.startswith("CON ")
    assert "Warri Mega Processors" in text1
    assert "1. Accept Offer" in text1

    # Turn 2: Accept offer (Option 1)
    resp2 = api_client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "AT_SESSION_005",
        "phoneNumber": farmer.phone_normalized,
        "text": "4*1"
    }, format='json')
    text2 = resp2.content.decode('utf-8')
    assert text2.startswith("END ")
    assert "Match ACCEPTED" in text2

    match.refresh_from_db()
    assert match.status == MatchStatus.CONFIRMED_BY_FARMER


@pytest.mark.django_db
def test_ussd_request_extension_visit(api_client, farmer_with_loan):
    """Option 5: Farmer requests an urgent extension visit via USSD menu."""
    farmer, farm, loan, cycle = farmer_with_loan

    payload = {
        "sessionId": "AT_SESSION_006",
        "phoneNumber": farmer.phone_normalized,
        "text": "5"
    }
    resp = api_client.post('/api/v1/alerts/ussd/', data=payload, format='json')
    assert resp.status_code == status.HTTP_200_OK
    text = resp.content.decode('utf-8')
    assert text.startswith("END ")
    assert "Extension visit requested" in text

    # Verify VisitAssignment created
    assignment = VisitAssignment.objects.filter(farm=farm).order_by('-created_at').first()
    assert assignment is not None
    assert assignment.priority_level == AssignmentPriority.HIGH
    assert "USSD" in assignment.instructions


@pytest.mark.django_db
def test_transactional_event_alerts(farmer_with_loan):
    """Tests automatic transactional SMS dispatches for harvest and loan reminders."""
    farmer, farm, loan, cycle = farmer_with_loan
    catfish = farm.enterprise_types.first()

    batch = ProduceBatch.objects.create(
        farm=farm,
        cycle=cycle,
        produce_type=catfish,
        projected_volume_kg=Decimal('2000.00'),
        projected_harvest_window_start=timezone.localdate() + timedelta(days=10),
        projected_harvest_window_end=timezone.localdate() + timedelta(days=20),
        status=ProduceBatchStatus.AVAILABLE
    )

    notif_harvest = notify_harvest_readiness(batch)
    assert notif_harvest is not None
    assert "harvest-ready" in notif_harvest.message_text
    assert "*384*223#" in notif_harvest.message_text

    notif_repay = notify_repayment_due(loan, days_overdue=7)
    assert notif_repay is not None
    assert "overdue balance" in notif_repay.message_text


@pytest.mark.django_db
def test_delivery_report_webhook_status_update(api_client):
    """Verifies that telecom delivery receipts update notification status to DELIVERED."""
    notif = send_transactional_sms("+2348039991234", "Test message")
    ref_id = notif.provider_reference

    callback_payload = {
        "id": ref_id,
        "status": "DeliveredToTerminal"
    }
    resp = api_client.post('/api/v1/alerts/sms/delivery-report/', data=callback_payload, format='json')
    assert resp.status_code == status.HTTP_200_OK

    notif.refresh_from_db()
    assert notif.status == AlertStatus.DELIVERED
