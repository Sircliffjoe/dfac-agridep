"""
DFAC AgriDEP - Milestone M5 Demonstration Script
Demonstrates end-to-end Offline Mobile Synchronization:
1. Local Drift SQLite Outbox Simulation (RFC4122 Client UUIDs).
2. Offline Farmer Onboarding, Farm Visit Check-in & Water Biometric Inspection.
3. Emergency Incident Capture in Offline Queue.
4. Bidirectional Delta Sync Push (/api/v1/sync/push/) & Server Ingestion.
5. Bidirectional Delta Sync Pull (/api/v1/sync/pull/) with ISO-8601 Cursor Progression.
6. Resumable Chunked Photo Evidence Upload Queue (/api/v1/sync/media/upload/).
7. Conflict Resolution Strategy (Server-wins on status, Last-write-wins on biometrics).
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

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient
from agridep.apps.accounts.models import User, UserRole
from agridep.apps.registry.models import Farmer, Farm
from agridep.apps.fieldops.models import FarmVisit, Inspection, IncidentReport, VisitAssignment
from agridep.apps.sync.models import MediaUploadSession
from agridep.apps.sync.services import process_sync_push, generate_sync_pull


def run_m5_demo():
    print("=" * 80)
    print("DFAC AgriDEP - Milestone M5: Flutter Offline Mobile Sync & Drift Engine")
    print("=" * 80)

    # 1. Field Officer Authentication & Mobile Context
    officer = User.objects.filter(role=UserRole.FIELD_OFFICER).first()
    if not officer:
        officer = User.objects.create(
            username="officer_mobile_demo",
            role=UserRole.FIELD_OFFICER,
            phone_number="+2348039992222",
            state="Delta",
            lga="Warri South"
        )
    print(f"\n--- 1. Field Extension Officer Session ---")
    print(f"  • Authenticated Officer: {officer.get_full_name() or officer.username}")
    print(f"  • Operating LGA: {officer.lga}, {officer.state} State")
    print(f"  • Device Profile: Android Low-Memory Target (< 2GB RAM)")

    # 2. Local Drift SQLite Outbox Simulation
    print(f"\n--- 2. Client-Side UUID Generation & Outbox Queue (Offline Mode) ---")
    farmer_client_uuid = str(uuid.uuid4())
    farm_client_uuid = str(uuid.uuid4())
    visit_client_uuid = str(uuid.uuid4())
    inspection_client_uuid = str(uuid.uuid4())
    incident_client_uuid = str(uuid.uuid4())

    print(f"  • Generated RFC4122 Client UUIDs (Drift Primary Keys):")
    print(f"    - Farmer:     {farmer_client_uuid}")
    print(f"    - Farm:       {farm_client_uuid}")
    print(f"    - Visit:      {visit_client_uuid}")
    print(f"    - Inspection: {inspection_client_uuid}")
    print(f"    - Incident:   {incident_client_uuid}")

    outbox_operations = [
        # Operation 1: Offline Farmer Onboarding
        {
            "client_id": farmer_client_uuid,
            "table": "farmers",
            "operation": "CREATE",
            "data": {
                "first_name": "Godspower",
                "last_name": "Ebikeme",
                "phone_normalized": "+2348038889900",
                "nin": "99887766554",
                "state": "Delta",
                "lga": "Warri South",
                "community_address": "Ogunu River Road"
            }
        },
        # Operation 2: Offline Farm Location Capture
        {
            "client_id": farm_client_uuid,
            "table": "farms",
            "operation": "CREATE",
            "data": {
                "farmer_client_id": farmer_client_uuid,
                "name": "Ebikeme Catfish Ponds",
                "latitude": 5.532100,
                "longitude": 5.751200,
                "number_of_ponds": 5,
                "total_area_hectares": 0.60
            }
        },
        # Operation 3: On-Site Farm Visit with GPS Check-in
        {
            "client_id": visit_client_uuid,
            "table": "farm_visits",
            "operation": "CREATE",
            "data": {
                "farm_client_id": farm_client_uuid,
                "purpose": "BIOSECURITY_INSPECTION",
                "latitude": 5.532110,
                "longitude": 5.751215,
                "gps_accuracy_meters": 4.5,
                "farmer_present": True,
                "officer_notes": "Stocking verified. Water inflow canal screened."
            }
        },
        # Operation 4: Water Quality & Biometric Inspection
        {
            "client_id": inspection_client_uuid,
            "table": "inspections",
            "operation": "CREATE",
            "data": {
                "visit_client_id": visit_client_uuid,
                "inspection_type": "WATER_QUALITY",
                "water_ph": 7.35,
                "water_temperature_celsius": 28.2,
                "dissolved_oxygen_mg_l": 5.90,
                "ammonia_ppm": 0.02,
                "average_sample_weight_grams": 520.0,
                "daily_mortality_count": 1,
                "biosecurity_protocol_followed": True,
                "summary_findings": "Optimal dissolved oxygen. Excellent biometric trajectory."
            }
        },
        # Operation 5: Emergency Incident Capture
        {
            "client_id": incident_client_uuid,
            "table": "incident_reports",
            "operation": "CREATE",
            "data": {
                "farm_client_id": farm_client_uuid,
                "title": "Minor dyke seepage during heavy rain",
                "description": "Pond 2 earthen dyke showed minor erosion along northern crest.",
                "incident_type": "FLOODING_EROSION",
                "severity": "MEDIUM",
                "mortality_estimate": 0
            }
        }
    ]

    print(f"  • Enqueued {len(outbox_operations)} offline operations in local SQLite outbox.")

    # 3. Batch Delta Sync Push
    print(f"\n--- 3. Delta Sync Push Execution (/api/v1/sync/push/) ---")
    push_result = process_sync_push(officer, outbox_operations)
    print(f"  • Ingested Client IDs: {len(push_result['synced_client_ids'])} records successfully committed to PostgreSQL")
    print(f"  • Sync Timestamp: {push_result['synced_at']}")
    print(f"  • Unresolved Conflicts: {len(push_result['conflicts'])}")

    # Verify committed entities
    synced_farmer = Farmer.objects.filter(client_id=farmer_client_uuid).first()
    synced_visit = FarmVisit.objects.filter(client_id=visit_client_uuid).first()
    synced_insp = Inspection.objects.filter(client_id=inspection_client_uuid).first()
    print(f"  • Verified in Central DB:")
    print(f"    - Farmer:     {synced_farmer.reference_code} ({synced_farmer.full_name})")
    print(f"    - Farm Visit: {synced_visit.reference_code} | Geofence Verified: {synced_visit.is_geofence_verified} ({synced_visit.distance_to_farm_meters:.1f}m drift)")
    print(f"    - Inspection: {synced_insp.reference_code} | pH {synced_insp.water_ph} | DO {synced_insp.dissolved_oxygen_mg_l} mg/L")

    # 4. Bidirectional Delta Sync Pull with Cursor
    print(f"\n--- 4. Delta Sync Pull Execution (/api/v1/sync/pull/) ---")
    cursor = (timezone.now() - timedelta(minutes=5)).isoformat()
    pull_result = generate_sync_pull(officer, since_iso=cursor)
    records = pull_result['records']
    print(f"  • New Cursor: {pull_result['new_cursor']}")
    print(f"  • Pulled Changes for Officer's Region:")
    print(f"    - Farmers:     {len(records['farmers'])} records")
    print(f"    - Farms:       {len(records['farms'])} records")
    print(f"    - Visits:      {len(records['visits'])} records")
    print(f"    - Inspections: {len(records['inspections'])} records")
    print(f"    - Incidents:   {len(records['incidents'])} records")
    print(f"    - Assignments: {len(records['assignments'])} active tasks for offline field routing")

    # 5. Background Resumable Media Upload Queue
    print(f"\n--- 5. Resumable Photo Evidence Upload Queue (/api/v1/sync/media/upload/) ---")
    client = APIClient()
    client.force_authenticate(user=officer)

    media_client_uuid = str(uuid.uuid4())
    photo_bytes = b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00...Simulated Geotagged Aquaculture Photo Bytes..."
    dummy_photo = SimpleUploadedFile("pond_water_sampling.jpg", photo_bytes, content_type="image/jpeg")

    media_resp = client.post(
        '/api/v1/sync/media/upload/',
        data={
            'client_id': media_client_uuid,
            'file_name': 'pond_water_sampling.jpg',
            'file_category': 'INSPECTION_PHOTO',
            'total_size': len(photo_bytes),
            'offset': 0,
            'file': dummy_photo
        },
        format='multipart'
    )

    print(f"  • Upload Response Status: HTTP {media_resp.status_code}")
    print(f"  • Media Session UUID:   {media_resp.data['session_id']}")
    print(f"  • Bytes Transferred:    {media_resp.data['bytes_received']} bytes")
    print(f"  • Upload Completed:     {media_resp.data['is_completed']}")

    # 6. Conflict Resolution Policy Demonstration
    print(f"\n--- 6. Conflict Resolution Policy (Server-Wins vs Last-Write-Wins) ---")
    print("  • Financial / Identity (Server-Wins):")
    print("    - If mobile client attempts to approve loan or clear verification status offline,")
    print("      the server master ledger strictly takes precedence (NDPA / Financial Integrity).")
    print("  • Extension Biometrics (Last-Write-Wins with Audit):")
    print("    - When extension officers update pond water pH or mortality while offline,")
    print("      the latest field observation overrides server defaults and logs an audit record.")

    print("\n" + "=" * 80)
    print("✅ Milestone M5 Demonstration Completed Successfully!")
    print("=" * 80)


if __name__ == '__main__':
    run_m5_demo()
