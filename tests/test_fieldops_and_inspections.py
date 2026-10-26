import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from agridep.apps.accounts.models import UserRole
from agridep.apps.registry.models import Farmer, Farm, EnterpriseType
from agridep.apps.production.models import ProductionCycle, ProduceBatch, ProduceBatchStatus
from agridep.apps.finance.models import RiskFlag, RiskSeverity
from agridep.apps.common.models import SystemParameter
from agridep.apps.fieldops.models import (
    FarmVisit,
    FarmVisitStatus,
    FarmVisitPurpose,
    Inspection,
    InspectionType,
    ComplianceRating,
    IncidentReport,
    IncidentSeverity,
    IncidentType,
    VisitAssignment,
    AssignmentPriority,
    AssignmentTrigger,
    AssignmentStatus,
)
from agridep.apps.fieldops.services import (
    haversine_distance_meters,
    verify_geofence,
    calculate_farm_priority_score,
    build_visit_priority_queue,
    auto_generate_visit_assignments,
    log_farm_visit,
    report_incident,
)

User = get_user_model()


@pytest.fixture
def field_officer(db):
    user = User.objects.create(
        username="officer_ughelli",
        role=UserRole.FIELD_OFFICER,
        state="Delta",
        lga="Ughelli North",
        phone_number="+2348039990001"
    )
    user.set_password("pass123")
    user.save()
    return user


@pytest.fixture
def dfac_admin(db):
    user = User.objects.create(
        username="admin_fieldops",
        role=UserRole.DFAC_ADMIN,
        is_staff=True,
        is_superuser=True,
        state="Delta",
        lga="Warri South",
        phone_number="+2348039990002"
    )
    user.set_password("pass123")
    user.save()
    return user


@pytest.fixture
def buyer_user(db):
    user = User.objects.create(
        username="buyer_isolated",
        role=UserRole.BUYER,
        phone_number="+2348039990003"
    )
    user.set_password("pass123")
    user.save()
    return user


@pytest.fixture
def farm_setup(db, field_officer):
    farmer = Farmer.objects.create(
        first_name="Tosan",
        last_name="Memudu",
        gender="MALE",
        state="Delta",
        lga="Ughelli North",
        assigned_officer=field_officer,
        phone_normalized="+2348031112222"
    )
    farm = Farm.objects.create(
        farmer=farmer,
        name="Memudu Catfish Clusters",
        latitude=Decimal("5.544230"),
        longitude=Decimal("5.760260"),
        community="Agbarho",
        number_of_ponds=6
    )
    enterprise = EnterpriseType.objects.create(name="African Catfish (Clarias)", category="AQUACULTURE")
    farm.enterprise_types.add(enterprise)
    return farm


@pytest.mark.django_db
def test_geofence_verification_on_site_and_drift(farm_setup):
    """Verifies that GPS coordinates close to farm pass geofencing, while distant coordinates trigger drift warning."""
    farm = farm_setup

    # Coordinates ~5 meters away
    on_site_lat = Decimal("5.544250")
    on_site_lon = Decimal("5.760270")
    is_verified, dist = verify_geofence(farm, on_site_lat, on_site_lon)
    assert is_verified is True
    assert dist < Decimal("15.00")

    # Coordinates ~2.5km away
    drift_lat = Decimal("5.560000")
    drift_lon = Decimal("5.780000")
    is_verified_drift, dist_drift = verify_geofence(farm, drift_lat, drift_lon)
    assert is_verified_drift is False
    assert dist_drift > Decimal("1000.00")


@pytest.mark.django_db
def test_dynamic_system_parameter_controls_geofence_threshold(farm_setup):
    """
    Confirms that admin parameter edits immediately change geofence rules in live execution
    without hardcoding.
    """
    farm = farm_setup

    # Coordinate ~250 meters away
    test_lat = Decimal("5.546000")
    test_lon = Decimal("5.761500")

    # Default is 150m: Should fail
    is_verified_default, dist = verify_geofence(farm, test_lat, test_lon)
    assert is_verified_default is False
    assert dist > Decimal("150.00")

    # Operator updates parameter in DB to 400m
    param, _ = SystemParameter.objects.get_or_create(key='fieldops_max_gps_drift_meters')
    param.value = '400'
    param.save()

    # Re-evaluate with exact same coordinates: Now passes!
    is_verified_updated, _ = verify_geofence(farm, test_lat, test_lon)
    assert is_verified_updated is True


@pytest.mark.django_db
def test_multi_factor_priority_queue_scoring(farm_setup, field_officer):
    """
    Tests dynamic scoring factors:
    - Overdue days past threshold
    - Financial risk flags
    - Pre-harvest window urgency
    - Open disease incidents
    """
    farm = farm_setup

    # 1. Base Score with fresh farm
    score_data_base = calculate_farm_priority_score(farm)
    assert score_data_base['total_score'] >= Decimal('0.00')

    # 2. Add an unresolved CRITICAL financial risk flag on farmer
    RiskFlag.objects.create(
        farmer=farm.farmer,
        severity=RiskSeverity.CRITICAL,
        rule_triggered="RULE-03",
        title="Severe Yield Deficit Risk"
    )

    # 3. Add an active batch with harvest window starting in 4 days
    today = timezone.localdate()
    catfish = farm.enterprise_types.first()
    cycle = ProductionCycle.objects.create(
        farm=farm,
        enterprise_type=catfish,
        cycle_name="Cycle 2026-A",
        start_date=today - timedelta(days=90),
        projected_harvest_date=today + timedelta(days=10),
        initial_stock_count=5000,
        current_stock_count=4800
    )
    ProduceBatch.objects.create(
        farm=farm,
        cycle=cycle,
        produce_type=catfish,
        projected_volume_kg=Decimal('4000.00'),
        projected_harvest_window_start=today + timedelta(days=4),
        projected_harvest_window_end=today + timedelta(days=12),
        status=ProduceBatchStatus.AVAILABLE
    )

    # 4. Add an active reported incident
    report_incident(
        farm=farm,
        reported_by=field_officer,
        title="Suspected parasite infestation",
        description="White spots observed on catfish bellies in Pond 1",
        incident_type=IncidentType.DISEASE_OUTBREAK,
        severity=IncidentSeverity.MEDIUM,
        auto_dispatch_visit=False
    )

    # Re-calculate score
    score_data = calculate_farm_priority_score(farm)
    # Expected: Risk (50.00) + Harvest (40.00) + Incident (30.00) = at least 120.00 points!
    assert score_data['total_score'] >= Decimal('120.00')
    assert score_data['priority_level'] == AssignmentPriority.URGENT


@pytest.mark.django_db
def test_emergency_incident_auto_dispatches_urgent_assignment(farm_setup, field_officer):
    """A CRITICAL incident must auto-dispatch an urgent VisitAssignment to the assigned extension officer."""
    farm = farm_setup

    initial_assignments = VisitAssignment.objects.filter(farm=farm).count()
    assert initial_assignments == 0

    incident = report_incident(
        farm=farm,
        reported_by=field_officer,
        title="Mass Catfish Mortality from Canal Pollution",
        description="Chemical discharge upstream caused immediate fish mortality in ponds 1 and 2.",
        incident_type=IncidentType.WATER_CONTAMINATION,
        severity=IncidentSeverity.CRITICAL,
        mortality_estimate=250,
        auto_dispatch_visit=True
    )

    assignment = VisitAssignment.objects.filter(farm=farm, status=AssignmentStatus.PENDING).first()
    assert assignment is not None
    assert assignment.priority_level == AssignmentPriority.URGENT
    assert assignment.assigned_officer == field_officer
    assert assignment.trigger_reason == AssignmentTrigger.CRITICAL_INCIDENT
    assert "EMERGENCY DISPATCH" in assignment.instructions


@pytest.mark.django_db
def test_log_farm_visit_and_fulfill_assignment(farm_setup, field_officer):
    """Logging a farm visit verifies geofence and completes any linked visit assignment."""
    farm = farm_setup

    assignment = VisitAssignment.objects.create(
        farm=farm,
        assigned_officer=field_officer,
        due_date=timezone.localdate(),
        priority_score=Decimal('65.00'),
        priority_level=AssignmentPriority.HIGH,
        trigger_reason=AssignmentTrigger.OVERDUE_ROUTINE,
        status=AssignmentStatus.PENDING
    )

    visit = log_farm_visit(
        farm=farm,
        officer=field_officer,
        latitude=farm.latitude,
        longitude=farm.longitude,
        purpose=FarmVisitPurpose.ROUTINE_EXTENSION,
        officer_notes="Biometrics sampled. Growth trajectory on target.",
        assignment=assignment
    )

    assert visit.is_geofence_verified is True
    assert visit.status == FarmVisitStatus.COMPLETED

    assignment.refresh_from_db()
    assert assignment.status == AssignmentStatus.COMPLETED


@pytest.mark.django_db
def test_fieldops_rbac_isolation(farm_setup, field_officer, dfac_admin, buyer_user):
    """
    RBAC Test:
    - Field Officer and DFAC Admin can access FieldOps API.
    - Buyer is strictly DENIED access to field operations (403 Forbidden).
    - Unauthenticated requests are rejected (401 Unauthorized).
    """
    client = APIClient()

    # 1. Unauthenticated -> 401
    res_unauth = client.get('/api/v1/fieldops/visits/')
    assert res_unauth.status_code == 401

    # 2. Buyer -> 403 Forbidden
    client.force_authenticate(user=buyer_user)
    res_buyer = client.get('/api/v1/fieldops/visits/')
    assert res_buyer.status_code == 403

    # 3. Field Officer -> 200 OK
    client.force_authenticate(user=field_officer)
    res_officer = client.get('/api/v1/fieldops/visits/')
    assert res_officer.status_code == 200

    # 4. Priority Queue endpoint
    res_pq = client.get('/api/v1/fieldops/priority-queue/')
    assert res_pq.status_code == 200
    assert 'results' in res_pq.data
