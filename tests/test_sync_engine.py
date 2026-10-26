import io
import uuid
from decimal import Decimal
import pytest
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from agridep.apps.registry.models import Farmer, Farm
from agridep.apps.production.models import ProductionCycle
from agridep.apps.fieldops.models import (
    FarmVisit,
    Inspection,
    IncidentReport,
    VisitAssignment,
    AssignmentPriority,
)
from agridep.apps.sync.models import IngestionLog, MediaUploadSession


@pytest.mark.django_db
def test_kobo_farmer_ingestion(api_client):
    payload = {
        "_id": 109283,
        "form_id": "farmer_registration",
        "first_name": "Koko",
        "last_name": "George",
        "phone": "+2348037771122",
        "nin": "55443322110",
        "state": "Bayelsa",
        "lga": "Yenagoa",
        "community": "Oxbow Lake",
        "latitude": 4.9312,
        "longitude": 6.2755,
        "number_of_ponds": 5
    }

    response = api_client.post('/api/v1/sync/kobo/', data=payload, format='json')
    assert response.status_code == status.HTTP_200_OK

    farmer = Farmer.objects.filter(phone_normalized="+2348037771122").first()
    assert farmer is not None
    assert farmer.first_name == "Koko"
    assert farmer.get_nin() == "55443322110"
    assert farmer.farms.count() == 1
    assert farmer.farms.first().number_of_ponds == 5

    # Check IngestionLog saved
    log = IngestionLog.objects.filter(submission_id="109283").first()
    assert log is not None
    assert log.processed_status == "SUCCESS"


@pytest.mark.django_db
def test_flutter_drift_sync_push_and_pull(api_client, officer_user):
    api_client.force_authenticate(user=officer_user)

    client_farmer_id = str(uuid.uuid4())
    client_farm_id = str(uuid.uuid4())

    push_payload = {
        "operations": [
            {
                "client_id": client_farmer_id,
                "table": "farmers",
                "operation": "CREATE",
                "data": {
                    "first_name": "Boma",
                    "last_name": "Jack",
                    "phone_normalized": "+2348034448899",
                    "nin": "77665544332",
                    "state": "Rivers",
                    "lga": "Port Harcourt",
                    "community_address": "Choba Creek"
                }
            },
            {
                "client_id": client_farm_id,
                "table": "farms",
                "operation": "CREATE",
                "data": {
                    "farmer_client_id": client_farmer_id,
                    "name": "Jack Catfish Farm",
                    "latitude": 4.8921,
                    "longitude": 6.9123,
                    "number_of_ponds": 6,
                    "total_area_hectares": 0.75
                }
            }
        ]
    }

    # 1. Push
    push_resp = api_client.post('/api/v1/sync/push/', data=push_payload, format='json')
    assert push_resp.status_code == status.HTTP_200_OK
    assert client_farmer_id in push_resp.data['synced_client_ids']
    assert client_farm_id in push_resp.data['synced_client_ids']

    # 2. Pull
    pull_resp = api_client.get('/api/v1/sync/pull/')
    assert pull_resp.status_code == status.HTTP_200_OK
    records = pull_resp.data['records']
    assert any(f['client_id'] == client_farmer_id for f in records['farmers'])


@pytest.mark.django_db
def test_flutter_drift_sync_push_visits_and_inspections(api_client, officer_user):
    """Verifies that offline completed visits and water chemistry audits sync cleanly."""
    api_client.force_authenticate(user=officer_user)

    farmer = Farmer.objects.create(
        first_name="Preye",
        last_name="Dickson",
        phone_normalized="+2348033334455",
        state="Delta",
        lga="Warri South",
        assigned_officer=officer_user
    )
    farm = Farm.objects.create(
        farmer=farmer,
        name="Dickson Aquaculture",
        latitude=Decimal("5.544200"),
        longitude=Decimal("5.760200")
    )

    client_visit_id = str(uuid.uuid4())
    client_inspection_id = str(uuid.uuid4())

    push_payload = {
        "operations": [
            {
                "client_id": client_visit_id,
                "table": "farm_visits",
                "operation": "CREATE",
                "data": {
                    "farm_id": str(farm.id),
                    "purpose": "BIOSECURITY_INSPECTION",
                    "latitude": 5.544210,
                    "longitude": 5.760210,
                    "officer_notes": "All ponds netted. Fingerlings active."
                }
            },
            {
                "client_id": client_inspection_id,
                "table": "inspections",
                "operation": "CREATE",
                "data": {
                    "visit_client_id": client_visit_id,
                    "inspection_type": "WATER_QUALITY",
                    "water_ph": 7.4,
                    "water_temperature_celsius": 28.0,
                    "dissolved_oxygen_mg_l": 6.1,
                    "average_sample_weight_grams": 450.0,
                    "daily_mortality_count": 0
                }
            }
        ]
    }

    resp = api_client.post('/api/v1/sync/push/', data=push_payload, format='json')
    assert resp.status_code == status.HTTP_200_OK
    assert client_visit_id in resp.data['synced_client_ids']
    assert client_inspection_id in resp.data['synced_client_ids']

    # Assert models in DB
    visit = FarmVisit.objects.filter(client_id=client_visit_id).first()
    assert visit is not None
    assert visit.is_geofence_verified is True
    assert visit.distance_to_farm_meters < Decimal("10.00")

    inspection = Inspection.objects.filter(client_id=client_inspection_id).first()
    assert inspection is not None
    assert inspection.water_ph == Decimal("7.40")
    assert inspection.dissolved_oxygen_mg_l == Decimal("6.10")


@pytest.mark.django_db
def test_flutter_drift_sync_push_emergency_incident(api_client, officer_user):
    """Verifies that an offline incident report syncs and triggers automatic urgent dispatch."""
    api_client.force_authenticate(user=officer_user)

    farmer = Farmer.objects.create(
        first_name="Amara",
        last_name="Okoro",
        phone_normalized="+2348035556677",
        state="Delta",
        lga="Warri South",
        assigned_officer=officer_user
    )
    farm = Farm.objects.create(
        farmer=farmer,
        name="Okoro Ponds",
        latitude=Decimal("5.520000"),
        longitude=Decimal("5.740000")
    )

    client_incident_id = str(uuid.uuid4())
    push_payload = {
        "operations": [
            {
                "client_id": client_incident_id,
                "table": "incident_reports",
                "operation": "CREATE",
                "data": {
                    "farm_id": str(farm.id),
                    "title": "Severe Low Oxygen Event from Heavy Siltation",
                    "description": "Canal water muddy after flooding. Fish gasping at water surface.",
                    "incident_type": "WATER_CONTAMINATION",
                    "severity": "CRITICAL",
                    "mortality_estimate": 60
                }
            }
        ]
    }

    resp = api_client.post('/api/v1/sync/push/', data=push_payload, format='json')
    assert resp.status_code == status.HTTP_200_OK

    incident = IncidentReport.objects.filter(client_id=client_incident_id).first()
    assert incident is not None
    assert incident.severity == "CRITICAL"

    # Emergency auto-dispatch created
    urgent_asn = VisitAssignment.objects.filter(farm=farm, priority_level=AssignmentPriority.URGENT).first()
    assert urgent_asn is not None


@pytest.mark.django_db
def test_resumable_media_chunk_upload(api_client, officer_user):
    """Verifies that photo evidence can be uploaded via the resumable media sync endpoint."""
    api_client.force_authenticate(user=officer_user)

    client_media_id = str(uuid.uuid4())
    file_content = b"Simulated JPEG photo bytes from mobile camera."
    dummy_file = SimpleUploadedFile("evidence_pond.jpg", file_content, content_type="image/jpeg")

    payload = {
        'client_id': client_media_id,
        'file_name': 'evidence_pond.jpg',
        'file_category': 'INSPECTION_PHOTO',
        'total_size': len(file_content),
        'offset': 0,
        'file': dummy_file
    }

    resp = api_client.post('/api/v1/sync/media/upload/', data=payload, format='multipart')
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data['client_id'] == client_media_id
    assert resp.data['is_completed'] is True

    # Assert MediaUploadSession in DB
    session = MediaUploadSession.objects.filter(client_id=client_media_id).first()
    assert session is not None
    assert session.bytes_received == len(file_content)
    assert session.is_completed is True
