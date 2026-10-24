import uuid
import pytest
from rest_framework import status
from agridep.apps.registry.models import Farmer, Farm
from agridep.apps.production.models import ProductionCycle
from agridep.apps.sync.models import IngestionLog

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
