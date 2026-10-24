import pytest
from decimal import Decimal
from rest_framework import status
from agridep.apps.registry.models import Farmer, Farm, VerificationStatus
from agridep.apps.accounts.models import User, UserRole

@pytest.mark.django_db
def test_buyer_pii_masking_before_match(api_client, buyer_user):
    farmer = Farmer.objects.create(
        first_name="Oghenekaro",
        last_name="Mudiaga",
        phone_normalized="+2348039991122",
        state="Delta",
        lga="Warri South",
        community_address="Secret Farm Waterfront",
        verification_status=VerificationStatus.VERIFIED
    )

    api_client.force_authenticate(user=buyer_user)
    response = api_client.get('/api/v1/registry/farmers/')

    assert response.status_code == status.HTTP_200_OK
    data = response.data.get('results', response.data)
    farmer_data = next((f for f in data if f['id'] == str(farmer.id)), None)

    assert farmer_data is not None
    # Assert buyer cannot see real name or phone
    assert farmer_data['first_name'] == "Smallholder"
    assert "Mudiaga" not in farmer_data['full_name']
    assert farmer_data['phone_normalized'] == "[Protected Contact]"
    assert farmer_data['community_address'] == "[Protected Address]"

@pytest.mark.django_db
def test_admin_full_access_unmasked(api_client, admin_user):
    farmer = Farmer.objects.create(
        first_name="Oghenekaro",
        last_name="Mudiaga",
        phone_normalized="+2348039991122",
        state="Delta",
        lga="Warri South",
        community_address="Secret Farm Waterfront"
    )

    api_client.force_authenticate(user=admin_user)
    response = api_client.get(f'/api/v1/registry/farmers/{farmer.id}/')

    assert response.status_code == status.HTTP_200_OK
    assert response.data['first_name'] == "Oghenekaro"
    assert response.data['last_name'] == "Mudiaga"
    assert response.data['phone_normalized'] == "+2348039991122"

@pytest.mark.django_db
def test_unauthenticated_denied(api_client):
    response = api_client.get('/api/v1/registry/farmers/')
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
