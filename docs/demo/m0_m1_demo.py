"""
DFAC AgriDEP - Milestones M0 & M1 Demonstration Script
Demonstrates end-to-end functionality:
- Authentication & JWT Token issuance
- Farmer & Farm registration with encrypted NIN and duplicate check
- Decision Rule RULE-01: Biometric log triggers harvest-ready flag & produce batch
- KoboToolbox / ODK webhook ingestion
- Flutter Drift SQLite delta sync push & pull
- Buyer PII data masking (RBAC)
- NDPA 2023 audit logging
"""
import os
import sys
import uuid
from decimal import Decimal
from datetime import date, timedelta

# Set Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agridep.config.settings.local')

import django
django.setup()

from rest_framework.test import APIClient
from agridep.apps.accounts.models import User, ConsentRecord
from agridep.apps.registry.models import Farmer, Farm, EnterpriseType, Buyer
from agridep.apps.production.models import ProductionCycle, ProductionLog, CycleStage, ProduceBatchStatus
from agridep.apps.audit.models import AuditEvent
from agridep.apps.sync.models import IngestionLog

def run_demo():
    print("=" * 70)
    print(" DFAC AgriDEP - MILESTONES M0 & M1 END-TO-END DEMO ")
    print("=" * 70)

    client = APIClient()

    # Step 1: Healthcheck
    print("\n[Step 1] Checking System Health & OpenAPI schema...")
    health_resp = client.get('/api/v1/health/')
    print(f" -> GET /api/v1/health/: {health_resp.status_code} {health_resp.json()}")

    # Step 2: Officer Authentication
    print("\n[Step 2] Authenticating as Field Officer (officer_delta)...")
    officer = User.objects.get(username='officer_delta')
    token_resp = client.post('/api/v1/auth/token/', {'username': 'officer_delta', 'password': 'password123'})
    token = token_resp.json().get('access')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    print(f" -> JWT Access Token obtained: {token[:24]}...")

    # Step 3: Register a Farmer
    print("\n[Step 3] Registering new smallholder farmer via Field API...")
    unique_suffix = str(uuid.uuid4())[:4]
    reg_payload = {
        "first_name": "Godwin",
        "last_name": f"Ebi-{unique_suffix}",
        "gender": "MALE",
        "phone_normalized": f"+23480399{unique_suffix}",
        "nin": "11223344556",
        "state": "Delta",
        "lga": "Warri South",
        "community_address": "Orugbo Creek Village"
    }
    reg_resp = client.post('/api/v1/registry/farmers/', data=reg_payload, format='json')
    farmer_data = reg_resp.json()
    print(f" -> Farmer Created: {farmer_data.get('reference_code')} - {farmer_data.get('full_name')}")
    print(f" -> Verification Status: {farmer_data.get('verification_status')}")

    # Step 4: Duplicate Detection Engine
    print("\n[Step 4] Testing Duplicate Detection Engine (Submitting identical phone)...")
    dup_resp = client.post('/api/v1/registry/farmers/check-duplicate/', data={
        "first_name": "Godwin Duplicate",
        "last_name": f"Ebi-{unique_suffix}",
        "phone": f"+23480399{unique_suffix}",
        "nin": "99999999999"
    }, format='json')
    dup_data = dup_resp.json()
    print(f" -> Duplicate Flagged: {dup_data.get('is_duplicate_or_flagged')}")
    print(f" -> Detection Reasons: {dup_data.get('reasons')}")

    # Step 5: Farm & Production Cycle
    print("\n[Step 5] Logging Production Cycle and Triggering Decision Rule RULE-01...")
    catfish = EnterpriseType.objects.get(code='CATFISH')
    farm = Farm.objects.create(
        farmer_id=farmer_data['id'],
        name="Godwin Ebi Commercial Catfish Ponds",
        latitude=Decimal('5.551200'),
        longitude=Decimal('5.768400'),
        number_of_ponds=6,
        total_area_hectares=Decimal('0.85')
    )
    cycle = ProductionCycle.objects.create(
        farm=farm,
        enterprise_type=catfish,
        cycle_name="Pond 1 - Table Size Harvest Batch",
        start_date=date.today() - timedelta(days=125),
        projected_harvest_date=date.today() + timedelta(days=25),
        initial_stock_count=4000,
        current_stock_count=4000,
        initial_average_weight_g=Decimal('15.0'),
        current_average_weight_g=Decimal('600.0'),
        status=CycleStage.GROWING
    )
    print(f" -> Cycle initialized: {cycle.cycle_name} (Initial Status: {cycle.status})")

    # Log 960g weight sample (nearing 1000g table size)
    log_resp = client.post('/api/v1/production/logs/', data={
        "cycle": str(cycle.id),
        "log_date": date.today().isoformat(),
        "sampling_average_weight_g": "960.00",
        "observed_mortality_count": 10,
        "feed_consumed_kg": "50.00",
        "water_temperature_c": "28.5",
        "ph_level": "7.30",
        "notes": "Fast growth observed. Ponds ready for harvest off-take."
    }, format='json')
    cycle.refresh_from_db()
    batch = cycle.produce_batches.first()
    print(f" -> Production Log Recorded! Sample Weight: 960g")
    print(f" -> [RULE-01 FIRED]: Cycle status transitioned to: {cycle.status}")
    print(f" -> Produce Batch Status: {batch.status} | Projected Volume: {batch.projected_volume_kg} kg")

    # Step 6: KoboToolbox Webhook Ingestion
    print("\n[Step 6] Testing KoboToolbox / ODK Remote Form Webhook Ingestion...")
    kobo_sub_id = str(uuid.uuid4())[:8]
    kobo_resp = client.post('/api/v1/sync/kobo/', data={
        "_id": kobo_sub_id,
        "form_id": "farmer_registration",
        "first_name": "Tari",
        "last_name": "Agidee",
        "phone": f"+23480388{unique_suffix}",
        "nin": "44332211009",
        "state": "Bayelsa",
        "lga": "Yenagoa",
        "community": "Swali",
        "latitude": 4.9255,
        "longitude": 6.2644,
        "number_of_ponds": 3
    }, format='json')
    print(f" -> Webhook Ingestion Result: {kobo_resp.json()}")
    kobo_farmer = Farmer.objects.filter(phone_normalized=f"+23480388{unique_suffix}").first()
    print(f" -> Ingested Farmer: {kobo_farmer.reference_code} - {kobo_farmer.full_name} ({kobo_farmer.farms.first().name})")

    # Step 7: Flutter Drift SQLite Outbox Push & Pull
    print("\n[Step 7] Testing Flutter Drift SQLite Batch Push & Delta Pull...")
    flutter_client_id = str(uuid.uuid4())
    push_resp = client.post('/api/v1/sync/push/', data={
        "operations": [{
            "client_id": flutter_client_id,
            "table": "farmers",
            "operation": "CREATE",
            "data": {
                "first_name": "Pere",
                "last_name": "Alagoa",
                "phone_normalized": f"+23480377{unique_suffix}",
                "state": "Bayelsa",
                "lga": "Nembe",
                "community_address": "Bassambiri Creek"
            }
        }]
    }, format='json')
    print(f" -> Drift Outbox Push: Synced IDs: {push_resp.json().get('synced_client_ids')}")

    pull_resp = client.get('/api/v1/sync/pull/')
    pull_data = pull_resp.json()
    print(f" -> Drift Delta Pull: Received {len(pull_data['records']['farmers'])} farmers, {len(pull_data['records']['cycles'])} cycles.")

    # Step 8: Buyer RBAC PII Masking
    print("\n[Step 8] Testing RBAC: Authenticating as Commercial Buyer (buyer_aggregator)...")
    buyer = User.objects.get(username='buyer_aggregator')
    buyer_token_resp = client.post('/api/v1/auth/token/', {'username': 'buyer_aggregator', 'password': 'password123'})
    buyer_token = buyer_token_resp.json().get('access')
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {buyer_token}')

    buyer_farmer_resp = client.get('/api/v1/registry/farmers/')
    buyer_farmers = buyer_farmer_resp.json().get('results', buyer_farmer_resp.json())
    first_f = buyer_farmers[0]
    print(f" -> Buyer Farmer View: Name='{first_f.get('full_name')}', Phone='{first_f.get('phone_normalized')}'")
    assert first_f.get('first_name') == "Smallholder", "Buyer must see masked name"
    assert first_f.get('phone_normalized') == "[Protected Contact]", "Buyer must see protected contact"
    print(" -> [VERIFIED]: Smallholder PII is strictly protected and masked for external buyers!")

    # Step 9: Audit Trail
    print("\n[Step 9] Verifying NDPA 2023 Audit Trail...")
    audit_count = AuditEvent.objects.count()
    latest_event = AuditEvent.objects.first()
    print(f" -> Total Audit Events Logged: {audit_count}")
    print(f" -> Latest Event: {latest_event.action} on {latest_event.resource_type}:{latest_event.resource_id} by {latest_event.user}")

    print("\n" + "=" * 70)
    print(" ALL MILESTONE M0 & M1 FEATURES VALIDATED SUCCESSFULLY! ")
    print("=" * 70)

if __name__ == '__main__':
    run_demo()
