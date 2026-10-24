import pytest
from decimal import Decimal
from rest_framework.test import APIClient
from agridep.apps.accounts.models import User, UserRole
from agridep.apps.registry.models import EnterpriseType, EnterpriseCategory, Cohort, Farmer, Farm, Buyer

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def admin_user(db):
    user = User.objects.create_superuser(
        username='test_admin',
        email='admin@test.ng',
        password='testpassword123',
        role=UserRole.DFAC_ADMIN
    )
    return user

@pytest.fixture
def officer_user(db):
    user = User.objects.create_user(
        username='test_officer',
        email='officer@test.ng',
        password='testpassword123',
        role=UserRole.FIELD_OFFICER,
        state='Delta',
        lga='Warri South'
    )
    return user

@pytest.fixture
def buyer_user(db):
    user = User.objects.create_user(
        username='test_buyer',
        email='buyer@test.ng',
        password='testpassword123',
        role=UserRole.BUYER
    )
    Buyer.objects.create(
        user=user,
        company_name='Test Seafood Aggregators',
        contact_name='Mr Test Buyer',
        phone='+2348039998877'
    )
    return user

@pytest.fixture
def catfish_enterprise(db):
    return EnterpriseType.objects.create(
        name='African Catfish',
        code='CATFISH',
        category=EnterpriseCategory.AQUACULTURE,
        standard_cycle_days=150,
        benchmark_fcr=Decimal('1.25'),
        expected_mortality_rate_pct=Decimal('7.50'),
        reference_price_per_kg_naira=Decimal('2500.00')
    )

@pytest.fixture
def delta_cohort(db, officer_user):
    return Cohort.objects.create(
        name='Delta Central Catfish Cohort',
        state='Delta',
        lga='Warri South',
        lead_officer=officer_user
    )
