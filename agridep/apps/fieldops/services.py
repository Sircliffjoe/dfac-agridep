import math
from datetime import date, timedelta
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from agridep.apps.common.models import SystemParameter
from agridep.apps.registry.models import Farm
from agridep.apps.production.models import ProduceBatch, ProduceBatchStatus
from agridep.apps.fieldops.models import (
    FarmVisit,
    FarmVisitStatus,
    FarmVisitPurpose,
    Inspection,
    InspectionPhoto,
    IncidentReport,
    IncidentSeverity,
    IncidentType,
    IncidentStatus,
    VisitAssignment,
    AssignmentPriority,
    AssignmentTrigger,
    AssignmentStatus,
)


def haversine_distance_meters(lat1, lon1, lat2, lon2) -> Decimal:
    """
    Computes great-circle distance between two GPS coordinates in meters
    using the spherical Haversine formula.
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return Decimal('999999.00')

    # Convert to radians
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))

    # Haversine formula
    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    earth_radius_meters = 6371000.0
    distance = earth_radius_meters * c
    return Decimal(str(round(distance, 2)))


def verify_geofence(farm: Farm, checkin_lat, checkin_lon) -> tuple[bool, Decimal]:
    """
    Verifies if a field officer's check-in coordinates are within the
    allowable radius of the registered farm coordinates.
    The drift threshold is dynamically managed via SystemParameter.
    """
    max_drift_meters = Decimal(str(SystemParameter.get(
        'fieldops_max_gps_drift_meters',
        default=150
    )))

    distance = haversine_distance_meters(
        farm.latitude,
        farm.longitude,
        checkin_lat,
        checkin_lon
    )

    is_verified = distance <= max_drift_meters
    return is_verified, distance


def calculate_farm_priority_score(farm: Farm) -> dict:
    """
    Dynamically scores a farm's visit priority using multi-factor weights
    retrieved from SystemParameter (Django Admin configurable):
      - W1: Days since last extension visit past threshold.
      - W2: Active credit/financial risk flags.
      - W3: Pre-harvest window urgency.
      - W4: Unresolved emergency disease/mortality incidents.
    """
    # 1. Load dynamic weights from SystemParameter
    w1_overdue_weight = Decimal(str(SystemParameter.get(
        'fieldops_priority_w1_overdue_weight', default=1.0
    )))
    overdue_threshold_days = int(SystemParameter.get(
        'fieldops_overdue_threshold_days', default=30
    ))
    overdue_max_days_cap = int(SystemParameter.get(
        'fieldops_overdue_max_days_cap', default=90
    ))

    w2_critical_risk = Decimal(str(SystemParameter.get(
        'fieldops_priority_w2_critical_risk_points', default=50.0
    )))
    w2_high_risk = Decimal(str(SystemParameter.get(
        'fieldops_priority_w2_high_risk_points', default=30.0
    )))
    w2_medium_risk = Decimal(str(SystemParameter.get(
        'fieldops_priority_w2_medium_risk_points', default=15.0
    )))
    w2_low_risk = Decimal(str(SystemParameter.get(
        'fieldops_priority_w2_low_risk_points', default=5.0
    )))

    w3_harvest_days = int(SystemParameter.get(
        'fieldops_priority_w3_harvest_days_threshold', default=10
    ))
    w3_harvest_score = Decimal(str(SystemParameter.get(
        'fieldops_priority_w3_harvest_score', default=40.0
    )))

    w4_incident_points = Decimal(str(SystemParameter.get(
        'fieldops_priority_w4_incident_points', default=30.0
    )))

    today = timezone.localdate()

    # 2. Factor 1: Overdue Days
    latest_visit = FarmVisit.objects.filter(
        farm=farm,
        status=FarmVisitStatus.COMPLETED
    ).order_by('-actual_visit_date', '-scheduled_date').first()

    if latest_visit and latest_visit.actual_visit_date:
        last_date = latest_visit.actual_visit_date.date()
    elif latest_visit:
        last_date = latest_visit.scheduled_date
    else:
        last_date = farm.created_at.date()

    days_since_visit = (today - last_date).days
    overdue_days = max(0, days_since_visit - overdue_threshold_days)
    capped_overdue_days = min(overdue_days, overdue_max_days_cap)
    score_overdue = Decimal(str(capped_overdue_days)) * w1_overdue_weight

    # 3. Factor 2: Financial Risk Flags on Farmer
    score_risk = Decimal('0.00')
    risk_flags_count = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    
    # Farmer can have risk flags
    if hasattr(farm.farmer, 'risk_flags'):
        unresolved_flags = farm.farmer.risk_flags.filter(is_resolved=False)
        for flag in unresolved_flags:
            sev = flag.severity.upper()
            if 'CRITICAL' in sev:
                score_risk += w2_critical_risk
                risk_flags_count['CRITICAL'] += 1
            elif 'HIGH' in sev:
                score_risk += w2_high_risk
                risk_flags_count['HIGH'] += 1
            elif 'MEDIUM' in sev:
                score_risk += w2_medium_risk
                risk_flags_count['MEDIUM'] += 1
            else:
                score_risk += w2_low_risk
                risk_flags_count['LOW'] += 1

    # 4. Factor 3: Pre-Harvest Urgency (RULE-01)
    score_harvest = Decimal('0.00')
    harvest_window_batches = ProduceBatch.objects.filter(
        farm=farm,
        status__in=[ProduceBatchStatus.FORECASTED, ProduceBatchStatus.AVAILABLE],
        projected_harvest_window_start__lte=today + timedelta(days=w3_harvest_days),
        projected_harvest_window_end__gte=today
    )
    is_harvest_imminent = harvest_window_batches.exists()
    if is_harvest_imminent:
        score_harvest = w3_harvest_score

    # 5. Factor 4: Active Open Incidents
    score_incidents = Decimal('0.00')
    open_incidents = IncidentReport.objects.filter(
        farm=farm,
        status__in=[IncidentStatus.REPORTED, IncidentStatus.INVESTIGATING]
    )
    incident_count = open_incidents.count()
    if incident_count > 0:
        score_incidents = Decimal(str(incident_count)) * w4_incident_points

    # 6. Aggregate Total Score
    total_score = score_overdue + score_risk + score_harvest + score_incidents

    # 7. Priority Level Classification
    if total_score >= Decimal('80.00'):
        priority_level = AssignmentPriority.URGENT
    elif total_score >= Decimal('50.00'):
        priority_level = AssignmentPriority.HIGH
    elif total_score >= Decimal('25.00'):
        priority_level = AssignmentPriority.MEDIUM
    else:
        priority_level = AssignmentPriority.LOW

    # 8. Primary Trigger Classification
    if open_incidents.filter(severity__in=[IncidentSeverity.CRITICAL, IncidentSeverity.HIGH]).exists():
        primary_trigger = AssignmentTrigger.CRITICAL_INCIDENT
    elif risk_flags_count['CRITICAL'] > 0 or risk_flags_count['HIGH'] > 0:
        primary_trigger = AssignmentTrigger.FINANCIAL_ARREARS
    elif is_harvest_imminent:
        primary_trigger = AssignmentTrigger.HARVEST_VERIFICATION
    elif score_overdue > Decimal('0.00'):
        primary_trigger = AssignmentTrigger.OVERDUE_ROUTINE
    else:
        primary_trigger = AssignmentTrigger.OVERDUE_ROUTINE

    return {
        'farm_id': str(farm.id),
        'farm_name': farm.name,
        'farmer_name': farm.farmer.full_name,
        'lga': farm.farmer.lga,
        'days_since_last_visit': days_since_visit,
        'overdue_days': overdue_days,
        'total_score': total_score,
        'priority_level': priority_level,
        'primary_trigger': primary_trigger,
        'scoring_breakdown': {
            'overdue_score': float(score_overdue),
            'risk_flags_score': float(score_risk),
            'harvest_score': float(score_harvest),
            'incident_score': float(score_incidents),
            'active_risks': risk_flags_count,
            'open_incidents': incident_count,
            'harvest_imminent': is_harvest_imminent,
        }
    }


def build_visit_priority_queue(officer=None, lga=None, limit=50) -> list[dict]:
    """
    Ranks farms in descending priority order based on dynamic multi-factor scoring.
    Optionally filtered by assigned extension officer or geographic LGA.
    """
    farms_qs = Farm.objects.select_related('farmer', 'farmer__assigned_officer').all()

    if officer is not None and not officer.is_superuser and officer.role != 'DFAC_ADMIN':
        farms_qs = farms_qs.filter(
            models.Q(farmer__assigned_officer=officer) |
            models.Q(farmer__lga=officer.lga)
        )
    elif lga:
        farms_qs = farms_qs.filter(farmer__lga=lga)

    ranked_items = []
    for farm in farms_qs:
        score_data = calculate_farm_priority_score(farm)
        ranked_items.append(score_data)

    # Sort descending by total_score
    ranked_items.sort(key=lambda item: item['total_score'], reverse=True)
    return ranked_items[:limit]


@transaction.atomic
def auto_generate_visit_assignments(officer=None, min_priority_threshold=Decimal('25.00')) -> list[VisitAssignment]:
    """
    Scans the priority queue and creates VisitAssignment dispatch orders
    for all farms that breach the priority threshold and have no active assignment.
    """
    ranked_queue = build_visit_priority_queue(officer=officer, limit=100)
    created_assignments = []
    today = timezone.localdate()

    for item in ranked_queue:
        if item['total_score'] < min_priority_threshold:
            continue

        farm = Farm.objects.get(id=item['farm_id'])

        # Check for existing active assignment
        active_assignment_exists = VisitAssignment.objects.filter(
            farm=farm,
            status__in=[AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED, AssignmentStatus.IN_PROGRESS]
        ).exists()

        if active_assignment_exists:
            continue

        # Determine target officer
        target_officer = farm.farmer.assigned_officer or officer
        if not target_officer:
            # Fallback to any active field officer in the same LGA or state
            from django.contrib.auth import get_user_model
            User = get_user_model()
            target_officer = User.objects.filter(
                role='FIELD_OFFICER',
                is_active=True
            ).first()

        if not target_officer:
            continue

        due_date = today + timedelta(days=2 if item['priority_level'] == AssignmentPriority.URGENT else 5)

        assignment = VisitAssignment.objects.create(
            farm=farm,
            assigned_officer=target_officer,
            due_date=due_date,
            priority_score=item['total_score'],
            priority_level=item['priority_level'],
            trigger_reason=item['primary_trigger'],
            status=AssignmentStatus.PENDING,
            auto_generated=True,
            scoring_breakdown=item['scoring_breakdown'],
            instructions=(
                f"Auto-dispatched via Decision Engine. Primary trigger: {item['primary_trigger']}. "
                f"Priority score: {item['total_score']}."
            )
        )
        created_assignments.append(assignment)

    return created_assignments


@transaction.atomic
def log_farm_visit(
    farm: Farm,
    officer,
    scheduled_date=None,
    actual_visit_date=None,
    purpose=FarmVisitPurpose.ROUTINE_EXTENSION,
    latitude=None,
    longitude=None,
    gps_accuracy_meters=Decimal('5.00'),
    farmer_present=True,
    officer_notes="",
    farmer_feedback="",
    assignment=None
) -> FarmVisit:
    """
    Records a completed extension visit with GPS check-in verification.
    If linked to a VisitAssignment, marks the assignment as COMPLETED.
    """
    if actual_visit_date is None:
        actual_visit_date = timezone.now()
    if scheduled_date is None:
        scheduled_date = actual_visit_date.date()

    is_verified = False
    distance_meters = None

    if latitude is not None and longitude is not None:
        is_verified, distance_meters = verify_geofence(farm, latitude, longitude)

    visit = FarmVisit.objects.create(
        farm=farm,
        officer=officer,
        scheduled_date=scheduled_date,
        actual_visit_date=actual_visit_date,
        status=FarmVisitStatus.COMPLETED,
        purpose=purpose,
        farmer_present=farmer_present,
        latitude=latitude,
        longitude=longitude,
        gps_accuracy_meters=gps_accuracy_meters,
        is_geofence_verified=is_verified,
        distance_to_farm_meters=distance_meters,
        officer_notes=officer_notes,
        farmer_feedback=farmer_feedback,
        linked_assignment=assignment
    )

    if assignment:
        assignment.status = AssignmentStatus.COMPLETED
        assignment.save(update_fields=['status', 'updated_at'])

    return visit


@transaction.atomic
def report_incident(
    farm: Farm,
    reported_by,
    title: str,
    description: str,
    incident_type=IncidentType.DISEASE_OUTBREAK,
    severity=IncidentSeverity.MEDIUM,
    produce_batch=None,
    mortality_estimate=0,
    financial_loss_estimate_ngn=Decimal('0.00'),
    immediate_actions_taken="",
    auto_dispatch_visit=True
) -> IncidentReport:
    """
    Logs an emergency incident report.
    For HIGH and CRITICAL incidents, automatically creates an urgent VisitAssignment
    dispatched to the assigned extension officer.
    """
    incident = IncidentReport.objects.create(
        farm=farm,
        reported_by=reported_by,
        produce_batch=produce_batch,
        incident_type=incident_type,
        severity=severity,
        status=IncidentStatus.REPORTED,
        title=title,
        description=description,
        mortality_estimate=mortality_estimate,
        financial_loss_estimate_ngn=financial_loss_estimate_ngn,
        immediate_actions_taken=immediate_actions_taken
    )

    # Auto-dispatch urgent visit assignment if severity is HIGH or CRITICAL
    if auto_dispatch_visit and severity in [IncidentSeverity.HIGH, IncidentSeverity.CRITICAL]:
        target_officer = farm.farmer.assigned_officer or reported_by
        due_date = timezone.localdate() + timedelta(days=1)

        VisitAssignment.objects.create(
            farm=farm,
            assigned_officer=target_officer,
            due_date=due_date,
            priority_score=Decimal('95.00') if severity == IncidentSeverity.CRITICAL else Decimal('75.00'),
            priority_level=AssignmentPriority.URGENT if severity == IncidentSeverity.CRITICAL else AssignmentPriority.HIGH,
            trigger_reason=AssignmentTrigger.CRITICAL_INCIDENT,
            status=AssignmentStatus.PENDING,
            auto_generated=True,
            scoring_breakdown={
                'incident_id': str(incident.id),
                'incident_severity': severity,
                'incident_type': incident_type,
            },
            instructions=f"EMERGENCY DISPATCH: {title}. Investigate immediately on-site."
        )

    return incident
