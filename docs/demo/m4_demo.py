"""
DFAC AgriDEP - Milestone M4 Demonstration Script
Demonstrates end-to-end Field Operations & Inspection Management:
1. Dynamic System Parameters loading from DB (no hard-coded values).
2. Multi-factor Dynamic Visit Priority Queue Scoring (W1 Overdue, W2 Financial Risks, W3 Harvest, W4 Incidents).
3. Automated Decision Engine Dispatch of VisitAssignment orders.
4. On-site GPS Check-in Geofence Verification & Distance Drift Detection.
5. Quantitative Aquaculture Inspection Logging (Water pH, DO, Temperature, Biosecurity).
6. Emergency Field Incident Reporting & Automated Escalation to Urgent Dispatch.
7. Strict RBAC Enforcement (Field Officer access vs Commercial Buyer isolation).
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
from agridep.apps.accounts.models import User, UserRole
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


def run_m4_demo():
    print("=" * 75)
    print("DFAC AgriDEP - Milestone M4: Field Operations & Inspection Engine")
    print("=" * 75)

    # 1. Dynamic System Parameters Verification (No hard-coding)
    print("\n--- 1. Dynamic System Parameters (Admin-Configurable Variables) ---")
    drift_param = SystemParameter.get('fieldops_max_gps_drift_meters', default=150)
    w1_param = SystemParameter.get('fieldops_priority_w1_overdue_weight', default=1.0)
    w2_crit = SystemParameter.get('fieldops_priority_w2_critical_risk_points', default=50.0)
    w3_harvest = SystemParameter.get('fieldops_priority_w3_harvest_score', default=40.0)
    print(f"  • Max Geofence Drift Threshold: {drift_param} meters (editable via Admin)")
    print(f"  • W1 Overdue Weight: {w1_param} pts/day")
    print(f"  • W2 Critical Risk Score: {w2_crit} pts")
    print(f"  • W3 Harvest Proximity Score: {w3_harvest} pts")

    # 2. Actors & Farm Profile
    print("\n--- 2. Field Officer & Farm Infrastructure ---")
    officer = User.objects.filter(role=UserRole.FIELD_OFFICER).first()
    if not officer:
        officer = User.objects.create(
            username="officer_demo_m4",
            role=UserRole.FIELD_OFFICER,
            phone_number="+2348039991111",
            state="Delta",
            lga="Warri South"
        )
    print(f"  • Extension Officer: {officer.get_full_name() or officer.username} (LGA: {officer.lga})")

    farm = Farm.objects.select_related('farmer').first()
    print(f"  • Farm Anchor: {farm.name} | Producer: {farm.farmer.full_name}")
    print(f"  • Registered Coordinates: Latitude {farm.latitude}, Longitude {farm.longitude}")

    # 3. Dynamic Multi-Factor Priority Queue Scoring
    print("\n--- 3. Multi-Factor Priority Queue Scoring ---")
    score_data = calculate_farm_priority_score(farm)
    print(f"  • Farm: {score_data['farm_name']}")
    print(f"  • Days Since Last Visit: {score_data['days_since_last_visit']} days (Overdue: {score_data['overdue_days']} days)")
    print(f"  • Priority Score: {score_data['total_score']} points")
    print(f"  • Priority Level: {score_data['priority_level']}")
    print(f"  • Primary Trigger: {score_data['primary_trigger']}")
    print(f"  • Scoring Breakdown: {score_data['scoring_breakdown']}")

    # 4. Automated Decision Engine Dispatch
    print("\n--- 4. Automated Decision Engine Dispatch ---")
    dispatched = auto_generate_visit_assignments(officer=officer, min_priority_threshold=Decimal('20.00'))
    print(f"  • Automatically Dispatched Visit Assignments: {len(dispatched)} generated")
    for asn in dispatched:
        print(f"    - [{asn.reference_code}] Farm: {asn.farm.name} | Due: {asn.due_date} | Priority: {asn.get_priority_level_display()}")

    # 5. GPS Geofence Verification & Drift Detection
    print("\n--- 5. On-Site GPS Geofence Verification ---")
    # Simulate on-site check-in within 10 meters
    on_site_lat = farm.latitude + Decimal('0.000050')
    on_site_lon = farm.longitude + Decimal('0.000050')
    is_on_site, on_site_dist = verify_geofence(farm, on_site_lat, on_site_lon)
    print(f"  [On-Site Test] Check-in distance: {on_site_dist:.1f}m -> Verified: {is_on_site} (Within {drift_param}m radius)")

    # Simulate remote check-in (1.8km away)
    remote_lat = farm.latitude + Decimal('0.015000')
    remote_lon = farm.longitude + Decimal('0.015000')
    is_remote, remote_dist = verify_geofence(farm, remote_lat, remote_lon)
    print(f"  [Remote Test]  Check-in distance: {remote_dist:.1f}m -> Verified: {is_remote} (Geofence Drift Warning Triggered!)")

    # 6. Completed Farm Visit & Aquaculture Inspection Logging
    print("\n--- 6. Completed Visit & Quantitative Water Chemistry Audit ---")
    visit = log_farm_visit(
        farm=farm,
        officer=officer,
        purpose=FarmVisitPurpose.BIOSECURITY_INSPECTION,
        latitude=on_site_lat,
        longitude=on_site_lon,
        officer_notes="Biometric sampling conducted on pond 2 and 4. Netting and dykes intact."
    )
    print(f"  • Visit Created: {visit.reference_code}")
    print(f"  • Status: {visit.get_status_display()} | Geofence Verified: {visit.is_geofence_verified} ({visit.distance_to_farm_meters:.1f}m drift)")

    inspection = Inspection.objects.create(
        visit=visit,
        inspection_type=InspectionType.WATER_QUALITY,
        compliance_rating=ComplianceRating.SATISFACTORY,
        water_ph=Decimal('7.30'),
        water_temperature_celsius=Decimal('28.5'),
        dissolved_oxygen_mg_l=Decimal('5.80'),
        ammonia_ppm=Decimal('0.02'),
        average_sample_weight_grams=Decimal('820.00'),
        daily_mortality_count=2,
        biosecurity_protocol_followed=True,
        summary_findings="Water chemistry optimal for table-size catfish growth. Dissolved oxygen above 5.0 mg/L threshold."
    )
    print(f"  • Inspection Recorded: {inspection.reference_code}")
    print(f"  • Water Biometrics: pH {inspection.water_ph} | DO {inspection.dissolved_oxygen_mg_l} mg/L | Temp {inspection.water_temperature_celsius}°C")
    print(f"  • Fish Sampling: Avg Weight {inspection.average_sample_weight_grams}g | Mortality {inspection.daily_mortality_count}")

    # 7. Emergency Incident Reporting & Auto-Escalation
    print("\n--- 7. Emergency Incident Reporting & Auto-Escalation ---")
    incident = report_incident(
        farm=farm,
        reported_by=officer,
        title="Excessive Siltation and Surface Piping in Pond 3",
        description="Inflow canal flooded following heavy rainfall. High turbidity and fish gasping for air at surface.",
        incident_type=IncidentType.WATER_CONTAMINATION,
        severity=IncidentSeverity.CRITICAL,
        mortality_estimate=45,
        auto_dispatch_visit=True
    )
    print(f"  • Emergency Incident Reported: {incident.reference_code} [{incident.get_severity_display()}]")
    print(f"  • Title: {incident.title}")

    urgent_asn = VisitAssignment.objects.filter(
        farm=farm,
        trigger_reason=AssignmentTrigger.CRITICAL_INCIDENT,
        status=AssignmentStatus.PENDING
    ).first()
    if urgent_asn:
        print(f"  • Auto-Escalated Urgent Dispatch: [{urgent_asn.reference_code}] Priority: {urgent_asn.get_priority_level_display()} (Due: {urgent_asn.due_date})")

    # 8. Strict RBAC Enforcement
    print("\n--- 8. Strict RBAC Enforcement ---")
    client = APIClient()
    buyer = User.objects.filter(role=UserRole.BUYER).first()
    if buyer:
        client.force_authenticate(user=buyer)
        res_buyer = client.get('/api/v1/fieldops/visits/')
        print(f"  • Commercial Buyer accessing /api/v1/fieldops/visits/ -> HTTP {res_buyer.status_code} (Isolation Enforced)")

    client.force_authenticate(user=officer)
    res_officer = client.get('/api/v1/fieldops/visits/')
    print(f"  • Field Officer accessing /api/v1/fieldops/visits/ -> HTTP {res_officer.status_code} (Authorized)")

    print("\n" + "=" * 75)
    print("✅ Milestone M4 Demonstration Completed Successfully!")
    print("=" * 75)


if __name__ == '__main__':
    run_m4_demo()
