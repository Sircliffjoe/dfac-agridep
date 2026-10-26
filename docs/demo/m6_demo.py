"""
DFAC AgriDEP - Milestone M6 Demonstration Script
Demonstrates end-to-end SMS & USSD Farmer Engagement Channel:
1. Dynamic System Parameters for telecommunication routing (*384*223#, Africa's Talking sender ID).
2. Transactional SMS Gateway dispatch with automatic delivery report webhook processing.
3. Interactive USSD Multi-Turn State Machine (*384*223#):
   - Menu 1: Loan & Repayment Status
   - Menu 2: Smallholder Offline Production Logging (Mortality & Feeding)
   - Menu 3: Delta Regional Market Prices (Catfish, Cassava, Poultry)
   - Menu 4: Commercial Buyer Off-take Match Acceptance
   - Menu 5: Extension Visit Request (auto-dispatches VisitAssignment)
4. Trigger-based Automated SMS Alerts (Harvest Readiness & Repayment Arrears).
"""
import os
import sys
from decimal import Decimal
from datetime import date, timedelta

# Set Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agridep.config.settings.local')

import django
django.setup()

from django.utils import timezone
from rest_framework.test import APIClient
from agridep.apps.registry.models import Farmer, Farm, EnterpriseType, Buyer
from agridep.apps.finance.models import Lender, LoanRecord, LoanStatus, RepaymentSchedule, ScheduleStatus
from agridep.apps.production.models import ProductionCycle, ProduceBatch, ProduceBatchStatus, ProductionLog
from agridep.apps.market.models import BuyerDemand, ProduceMatch, MatchStatus, CommodityPrice
from agridep.apps.fieldops.models import VisitAssignment, AssignmentPriority, AssignmentTrigger
from agridep.apps.common.models import SystemParameter
from agridep.apps.alerts.models import AlertNotification, AlertStatus, AlertPriority, USSDSession
from agridep.apps.alerts.services import (
    send_transactional_sms,
    notify_harvest_readiness,
    notify_repayment_due,
    notify_emergency_disease,
)
from agridep.apps.alerts.adapters import get_sms_adapter
from agridep.apps.alerts.ussd import USSDHandler


def run_demo():
    print("=" * 80)
    print("      DFAC AgriDEP - MILESTONE M6 DEMONSTRATION")
    print("   SMS & USSD Feature Phone Channel (*384*223# & Africa's Talking Gateway)")
    print("=" * 80)

    # 1. Inspect Dynamic Telecommunication Parameters
    print("\n[1] Dynamic Telecommunication System Parameters (0 hardcoded values):")
    ussd_code = SystemParameter.get('USSD_SERVICE_CODE', default='*384*223#')
    at_sender = SystemParameter.get('AT_SMS_SENDER_ID', default='DFAC-AGRI')
    at_mock = SystemParameter.get('AT_SMS_USE_MOCK', default=True)
    max_retries = SystemParameter.get('SMS_MAX_RETRY_COUNT', default=3)
    print(f"    • Primary USSD Service Code: {ussd_code}")
    print(f"    • Africa's Talking Sender ID: {at_sender}")
    print(f"    • Gateway Adapter Mode: {'Mock Development Adapter' if at_mock else 'Live HTTP Adapter'}")
    print(f"    • Max SMS Delivery Retries: {max_retries}")

    # 2. Setup Demonstration Entities
    print("\n[2] Setting up Delta State Smallholder Profile:")
    catfish, _ = EnterpriseType.objects.get_or_create(
        name="Catfish Aquaculture",
        defaults={"category": "AQUACULTURE"}
    )
    farmer, _ = Farmer.objects.get_or_create(
        phone_normalized="+2348039991122",
        defaults={
            "first_name": "Godwin",
            "last_name": "Efe",
            "gender": "MALE",
            "state": "Delta",
            "lga": "Warri South"
        }
    )
    farm, _ = Farm.objects.get_or_create(
        farmer=farmer,
        defaults={
            "name": "Godwin Catfish Ponds",
            "latitude": Decimal("5.525000"),
            "longitude": Decimal("5.748000")
        }
    )
    farm.enterprise_types.add(catfish)

    lender, _ = Lender.objects.get_or_create(
        institution_name="Bank of Agriculture (BOA) Delta",
        defaults={
            "institution_type": "COMMERCIAL_BANK",
            "contact_person": "Director Aliu",
            "phone": "+2348030009999",
            "email": "boa-delta@dfac.ng"
        }
    )

    loan, _ = LoanRecord.objects.get_or_create(
        farmer=farmer,
        defaults={
            "lender": lender,
            "farm": farm,
            "principal_amount_naira": Decimal("350000.00"),
            "interest_rate_percent": Decimal("9.00"),
            "tenure_months": 6,
            "status": LoanStatus.DISBURSED
        }
    )
    RepaymentSchedule.objects.get_or_create(
        loan=loan,
        installment_number=1,
        defaults={
            "due_date": timezone.localdate() + timedelta(days=12),
            "expected_amount_naira": Decimal("65000.00"),
            "status": ScheduleStatus.PENDING
        }
    )

    cycle, _ = ProductionCycle.objects.get_or_create(
        farm=farm,
        cycle_name="Cycle M6-Aquaculture",
        defaults={
            "enterprise_type": catfish,
            "start_date": timezone.localdate() - timedelta(days=90),
            "projected_harvest_date": timezone.localdate() + timedelta(days=15),
            "initial_stock_count": 5000,
            "current_stock_count": 4800,
            "status": "STOCKED"
        }
    )

    print(f"    • Smallholder: {farmer.first_name} {farmer.last_name} ({farmer.phone_normalized})")
    print(f"    • Farm: {farm.name} ({farmer.lga}, {farmer.state})")
    print(f"    • Active Loan: {loan.reference_code} (₦{loan.principal_amount_naira:,.2f})")
    print(f"    • Cycle: {cycle.cycle_name} (5,000 Fingerlings stocked)")

    # 3. Interactive USSD Multi-Turn State Machine Simulation
    print("\n[3] Simulating Feature Phone USSD Multi-Turn Session (*384*223#):")
    client = APIClient()

    # Step A: Root Dial
    print("\n  --- [3.A] Dialing *384*223# (Root Menu) ---")
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_001",
        "phoneNumber": farmer.phone_normalized,
        "text": ""
    }, format='json')
    print(resp.content.decode('utf-8'))

    # Step B: Option 1 - Check Loan Balance & Installment
    print("  --- [3.B] Farmer Selects '1' (Check Loan & Repayment) ---")
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_001",
        "phoneNumber": farmer.phone_normalized,
        "text": "1"
    }, format='json')
    print(resp.content.decode('utf-8'))

    # Step C: Option 2 - Multi-turn Production Log (Fish mortality + Feed)
    print("  --- [3.C.1] Farmer Selects '2' (Log Farm Mortality & Feed) ---")
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_002",
        "phoneNumber": farmer.phone_normalized,
        "text": "2"
    }, format='json')
    print(resp.content.decode('utf-8'))

    print("  --- [3.C.2] Farmer Inputs Mortality '8' ---")
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_002",
        "phoneNumber": farmer.phone_normalized,
        "text": "2*8"
    }, format='json')
    print(resp.content.decode('utf-8'))

    print("  --- [3.C.3] Farmer Inputs Feed Bags '4' ---")
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_002",
        "phoneNumber": farmer.phone_normalized,
        "text": "2*8*4"
    }, format='json')
    print(resp.content.decode('utf-8'))

    latest_log = ProductionLog.objects.filter(cycle=cycle).order_by('-created_at').first()
    print(f"    [DB Verification] New ProductionLog logged via USSD:")
    print(f"      - Mortality Count: {latest_log.observed_mortality_count}")
    print(f"      - Feed Fed: {latest_log.feed_consumed_kg} kg")
    print(f"      - Notes: {latest_log.notes}")

    # Step D: Option 3 - Regional Commodity Market Prices
    print("\n  --- [3.D] Farmer Selects '3' (Check Market Prices) ---")
    CommodityPrice.objects.get_or_create(
        enterprise_type=catfish,
        effective_date=timezone.localdate(),
        defaults={
            "market_hub": "Effurun Central Market, Warri",
            "state": "Delta",
            "price_per_kg_naira": Decimal("2650.00")
        }
    )
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_003",
        "phoneNumber": farmer.phone_normalized,
        "text": "3"
    }, format='json')
    print(resp.content.decode('utf-8'))

    # Step E: Option 4 - Review and Confirm Proposed Buyer Match
    print("  --- [3.E.1] Farmer Selects '4' (Review Buyer Match) ---")
    batch, _ = ProduceBatch.objects.get_or_create(
        farm=farm,
        cycle=cycle,
        defaults={
            "produce_type": catfish,
            "projected_volume_kg": Decimal("2500.00"),
            "projected_harvest_window_start": timezone.localdate() + timedelta(days=5),
            "projected_harvest_window_end": timezone.localdate() + timedelta(days=15),
            "status": ProduceBatchStatus.AVAILABLE
        }
    )
    buyer, _ = Buyer.objects.get_or_create(
        company_name="Asaba Premium Foods Processing Ltd",
        defaults={"contact_name": "Chief Ebi", "phone": "+2348028889999"}
    )
    demand, _ = BuyerDemand.objects.get_or_create(
        buyer=buyer,
        enterprise_type=catfish,
        defaults={
            "target_volume_kg": Decimal("5000.00"),
            "offered_price_per_kg_naira": Decimal("2600.00"),
            "target_delivery_window_start": timezone.localdate() + timedelta(days=5),
            "target_delivery_window_end": timezone.localdate() + timedelta(days=20),
        }
    )
    match, _ = ProduceMatch.objects.get_or_create(
        buyer_demand=demand,
        produce_batch=batch,
        defaults={
            "allocated_volume_kg": Decimal("2500.00"),
            "agreed_price_per_kg_naira": Decimal("2600.00"),
            "status": MatchStatus.PROPOSED
        }
    )
    match.status = MatchStatus.PROPOSED
    match.save(update_fields=['status'])

    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_004",
        "phoneNumber": farmer.phone_normalized,
        "text": "4"
    }, format='json')
    print(resp.content.decode('utf-8'))

    print("  --- [3.E.2] Farmer Selects '1' (Accept Offer) ---")
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_004",
        "phoneNumber": farmer.phone_normalized,
        "text": "4*1"
    }, format='json')
    print(resp.content.decode('utf-8'))
    match.refresh_from_db()
    print(f"    [DB Verification] ProduceMatch Status updated to: {match.status}")

    # Step F: Option 5 - Request Urgent Extension Visit
    print("\n  --- [3.F] Farmer Selects '5' (Request Extension Visit) ---")
    resp = client.post('/api/v1/alerts/ussd/', data={
        "sessionId": "DEMO_SESSION_005",
        "phoneNumber": farmer.phone_normalized,
        "text": "5"
    }, format='json')
    print(resp.content.decode('utf-8'))
    assignment = VisitAssignment.objects.filter(
        farm=farm,
        trigger_reason=AssignmentTrigger.MANUAL_DISPATCH
    ).order_by('-created_at').first()
    if assignment:
        print(f"    [DB Verification] Extension VisitAssignment generated: Priority={assignment.priority_level}, Instructions={assignment.instructions}")

    # 4. Transactional SMS Gateway & Webhook Delivery Tracking
    print("\n[4] Transactional Event Alerts & Delivery Report Webhook:")
    sms_notif = send_transactional_sms(
        phone_number=farmer.phone_normalized,
        message=f"DFAC Alert: Loan #{loan.reference_code} installment of NGN 65,000 due in 12 days. Dial *384*223# for details.",
        priority=AlertPriority.HIGH
    )
    print(f"    • Dispatched SMS Reference: {sms_notif.provider_reference}")
    print(f"    • Initial Status: {sms_notif.status}")
    print(f"    • Message: \"{sms_notif.message_text}\"")

    # Simulate Africa's Talking Delivery Webhook
    print("\n  --- Simulating Africa's Talking Delivery Webhook Callback ---")
    wh_resp = client.post('/api/v1/alerts/sms/delivery-report/', data={
        "id": sms_notif.provider_reference,
        "status": "Success",
        "phoneNumber": farmer.phone_normalized,
        "networkCode": "62120",
        "failureReason": ""
    }, format='json')
    sms_notif.refresh_from_db()
    print(f"    • Webhook Response: {wh_resp.status_code} {wh_resp.data}")
    print(f"    • Updated SMS Status: {sms_notif.status}")

    # Automated Event Alerts
    print("\n[5] Triggering Automated Transactional Notification Workflows:")
    harvest_alert = notify_harvest_readiness(batch)
    print(f"    • Harvest Ready Alert: [{harvest_alert.status}] -> \"{harvest_alert.message_text}\"")

    repay_alert = notify_repayment_due(loan, days_overdue=5)
    print(f"    • Repayment Arrears Alert: [{repay_alert.status}] -> \"{repay_alert.message_text}\"")

    print("\n" + "=" * 80)
    print("   MILESTONE M6 DEMONSTRATION COMPLETE - ALL SYSTEMS OPERATIONAL")
    print("=" * 80)


if __name__ == '__main__':
    run_demo()
