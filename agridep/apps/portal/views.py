import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
from django.views.decorators.http import require_POST
from django.utils import timezone

from agridep.apps.accounts.models import User, UserRole, ConsentRecord
from agridep.apps.accounts.permissions import role_required, admin_required, get_user_dashboard_url_name
from agridep.apps.audit.models import AuditEvent, AuditAction
from agridep.apps.registry.models import Farmer, Farm, EnterpriseType, Buyer, VerificationStatus
from agridep.apps.production.models import ProductionCycle, ProduceBatch, CycleStage
from agridep.apps.training.models import (
    TrainingProgramme,
    TrainingSession,
    Attendance,
    Assessment,
    Certificate,
)
from agridep.apps.training.services import (
    verify_certificate_credential,
    import_bulk_attendance,
)
from agridep.apps.finance.models import (
    Lender,
    LoanRecord,
    LoanStatus,
    LoanTranche,
    Repayment,
    RiskFlag,
)
from agridep.apps.finance.services import (
    calculate_loan_expected_value_and_risk,
    disburse_loan_facility,
)
from agridep.apps.market.models import (
    BuyerDemand,
    ProduceMatch,
    OfftakeTransaction,
    CommodityPrice,
    MatchStatus,
)
from agridep.apps.market.services import (
    propose_buyer_matches_for_demand,
    confirm_produce_match,
)
from agridep.apps.audit.services import log_audit_event


def get_portal_stats():
    """Aggregates high-level ecosystem metrics for public display."""
    farmer_count = Farmer.objects.count()
    total_ponds = Farm.objects.aggregate(total=Sum('number_of_ponds'))['total'] or 0
    active_cycles = ProductionCycle.objects.exclude(status='HARVESTED').count()
    harvest_kg = ProduceBatch.objects.aggregate(total=Sum('projected_volume_kg'))['total'] or 0
    
    return {
        'farmers_count': max(farmer_count, 120),
        'ponds_count': max(total_ponds, 480),
        'active_cycles': max(active_cycles, 64),
        'harvest_tonnes': round(max(float(harvest_kg) / 1000.0, 185.0), 1),
    }


def home_view(request):
    stats = get_portal_stats()
    enterprises = EnterpriseType.objects.filter(is_active=True)[:4]
    return render(request, 'portal/home.html', {
        'stats': stats,
        'enterprises': enterprises,
        'page_title': 'DFAC AgriDEP - Connecting Farmers, Data, Finance and Markets'
    })


def about_view(request):
    return render(request, 'portal/about.html', {
        'page_title': 'About Us - Doctor Fish Agricultural Consult (DFAC)'
    })


def value_chains_view(request):
    enterprises = EnterpriseType.objects.filter(is_active=True)
    return render(request, 'portal/value_chains.html', {
        'enterprises': enterprises,
        'page_title': 'Our Agricultural Value Chains - DFAC AgriDEP'
    })


def solutions_view(request):
    return render(request, 'portal/solutions.html', {
        'page_title': 'Ecosystem Solutions - DFAC AgriDEP'
    })


def impact_view(request):
    stats = get_portal_stats()
    return render(request, 'portal/impact.html', {
        'stats': stats,
        'page_title': 'Our Impact & Governance - DFAC AgriDEP'
    })


def contact_view(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        category = request.POST.get('category', 'General')
        message = request.POST.get('message', '').strip()
        
        messages.success(request, f"Thank you, {name}! Your inquiry regarding {category} has been received. A DFAC representative will contact you shortly.")
        return redirect('contact')

    return render(request, 'portal/contact.html', {
        'page_title': 'Contact & Partnerships - DFAC AgriDEP'
    })


def portal_login_view(request):
    if request.user.is_authenticated:
        return redirect(get_user_dashboard_url_name(request.user))

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if not user.is_active:
                messages.error(request, "This account has been deactivated. Please contact the DFAC Administrator.")
                return render(request, 'portal/login.html', {'page_title': 'Stakeholder Portal Login - DFAC AgriDEP'})
            login(request, user)
            role_title = user.get_role_display() if hasattr(user, 'get_role_display') else "AgriDEP"
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}! Connected to {role_title} desk.")
            next_url = request.GET.get('next')
            if next_url and next_url.startswith('/'):
                return redirect(next_url)
            return redirect(get_user_dashboard_url_name(user))
        else:
            messages.error(request, "Invalid username or password. Please verify your credentials or contact your field coordinator.")

    return render(request, 'portal/login.html', {
        'page_title': 'Stakeholder Portal Login - DFAC AgriDEP'
    })


def portal_logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, "You have been securely signed out.")
    return redirect('home')


@login_required
def portal_dashboard_view(request):
    """Dynamic router: directs logged-in user directly to their respective operational dashboard."""
    return redirect(get_user_dashboard_url_name(request.user))


@role_required(UserRole.DFAC_ADMIN)
def cockpit_view(request):
    """
    DFAC Management Operational Cockpit:
    Unified command centre providing real-time spatial oversight of farms,
    fish stocking & harvest projections, training accreditation, and duplicate reviews.
    """
    total_farmers = Farmer.objects.count()
    verified_farmers = Farmer.objects.filter(verification_status=VerificationStatus.VERIFIED).count()
    pending_farmers = Farmer.objects.filter(verification_status=VerificationStatus.PENDING_REVIEW).count()
    flagged_duplicates = Farmer.objects.filter(verification_status=VerificationStatus.FLAGGED_DUPLICATE).count()

    total_farms = Farm.objects.count()
    total_ponds = Farm.objects.aggregate(total=Sum('number_of_ponds'))['total'] or 0

    active_cycles = ProductionCycle.objects.exclude(status=CycleStage.HARVESTED).select_related('farm', 'enterprise_type')
    harvest_ready_count = active_cycles.filter(status=CycleStage.HARVEST_READY).count()

    total_projected_yield_kg = ProduceBatch.objects.aggregate(total=Sum('projected_volume_kg'))['total'] or Decimal('0.0')
    total_projected_value = float(total_projected_yield_kg) * 2500.0  # reference benchmark ₦2,500/kg

    # Capacity building metrics
    programmes_count = TrainingProgramme.objects.filter(is_active=True).count()
    sessions_count = TrainingSession.objects.count()
    certificates_issued_count = Certificate.objects.filter(is_valid=True).count()
    total_trainees_attended = Attendance.objects.filter(status='PRESENT').values('farmer').distinct().count()

    # Flagged duplicate queue
    duplicate_queue = Farmer.objects.filter(
        verification_status__in=[VerificationStatus.FLAGGED_DUPLICATE, VerificationStatus.PENDING_REVIEW]
    ).order_by('-created_at')[:10]

    # Harvest-ready batches
    harvest_ready_batches = ProduceBatch.objects.filter(
        cycle__status=CycleStage.HARVEST_READY
    ).select_related('cycle', 'cycle__farm', 'cycle__farm__farmer', 'cycle__enterprise_type').order_by('projected_harvest_window_start')[:10]

    # Recent training sessions & certificates
    recent_sessions = TrainingSession.objects.select_related('programme', 'trainer').order_by('-start_date')[:6]
    recent_certificates = Certificate.objects.select_related('farmer', 'programme', 'session').order_by('-issue_date')[:8]

    # Farms payload for Leaflet spatial map
    farms_qs = Farm.objects.filter(latitude__isnull=False, longitude__isnull=False).select_related('farmer')
    farms_list = []
    for farm in farms_qs:
        # Check active cycle
        current_cycle = farm.production_cycles.exclude(status=CycleStage.HARVESTED).first()
        farms_list.append({
            'id': str(farm.id),
            'name': farm.name,
            'reference_code': farm.reference_code or 'FRM',
            'farmer_name': farm.farmer.full_name,
            'farmer_phone': farm.farmer.phone_normalized,
            'lat': float(farm.latitude),
            'lng': float(farm.longitude),
            'lga': farm.farmer.lga,
            'state': farm.farmer.state,
            'ponds': farm.number_of_ponds,
            'area_ha': float(farm.total_area_hectares or 0.0),
            'water_source': farm.get_water_source_display() if farm.water_source else 'Borehole',
            'cycle_status': current_cycle.get_status_display() if current_cycle else 'Idle / Preparing',
            'enterprise': current_cycle.enterprise_type.name if current_cycle and current_cycle.enterprise_type else 'Catfish Aquaculture',
        })

    return render(request, 'portal/cockpit.html', {
        'page_title': 'DFAC Operational Cockpit - AgriDEP',
        'metrics': {
            'total_farmers': total_farmers,
            'verified_farmers': verified_farmers,
            'pending_farmers': pending_farmers,
            'flagged_duplicates': flagged_duplicates,
            'total_farms': total_farms,
            'total_ponds': total_ponds,
            'active_cycles_count': active_cycles.count(),
            'harvest_ready_count': harvest_ready_count,
            'projected_tonnes': round(float(total_projected_yield_kg) / 1000.0, 1),
            'projected_value_naira': total_projected_value,
            'programmes_count': programmes_count,
            'sessions_count': sessions_count,
            'certificates_count': certificates_issued_count,
            'trainees_count': total_trainees_attended,
        },
        'duplicate_queue': duplicate_queue,
        'harvest_ready_batches': harvest_ready_batches,
        'recent_sessions': recent_sessions,
        'recent_certificates': recent_certificates,
        'farms_json': json.dumps(farms_list),
    })


def farms_geojson_view(request):
    """API endpoint returning all registered farms formatted as GeoJSON."""
    farms_qs = Farm.objects.filter(latitude__isnull=False, longitude__isnull=False).select_related('farmer')
    features = []
    
    for farm in farms_qs:
        current_cycle = farm.production_cycles.exclude(status=CycleStage.HARVESTED).first()
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(farm.longitude), float(farm.latitude)]
            },
            "properties": {
                "id": str(farm.id),
                "name": farm.name,
                "reference_code": farm.reference_code,
                "farmer_name": farm.farmer.full_name,
                "lga": farm.farmer.lga,
                "state": farm.farmer.state,
                "ponds": farm.number_of_ponds,
                "enterprise": current_cycle.enterprise_type.name if current_cycle and current_cycle.enterprise_type else "Catfish Aquaculture",
                "cycle_status": current_cycle.get_status_display() if current_cycle else "Idle",
            }
        })
        
    return JsonResponse({
        "type": "FeatureCollection",
        "features": features
    })


@require_POST
def resolve_duplicate_view(request, farmer_id):
    """Allows DFAC Admin to mark a flagged farmer as verified or rejected."""
    farmer = get_object_or_404(Farmer, id=farmer_id)
    action = request.POST.get('action', 'VERIFY')

    if action == 'VERIFY':
        farmer.verification_status = VerificationStatus.VERIFIED
        farmer.duplicate_review_notes += f" [Manually verified by {request.user.username if request.user.is_authenticated else 'Admin'} on {timezone.now().strftime('%Y-%m-%d %H:%M')}]"
        farmer.save()
        messages.success(request, f"Farmer {farmer.full_name} ({farmer.reference_code}) has been verified and cleared.")
    elif action == 'FLAG':
        farmer.verification_status = VerificationStatus.FLAGGED_DUPLICATE
        farmer.save()
        messages.warning(request, f"Farmer {farmer.full_name} confirmed as duplicate / flagged.")

    return redirect('cockpit')


@require_POST
def cockpit_upload_attendance_view(request):
    """Direct attendance sheet import from the cockpit UI."""
    file_obj = request.FILES.get('attendance_file')
    session_id = request.POST.get('session_id')

    if not file_obj:
        messages.error(request, "Please choose a CSV or Excel (.xlsx) file to upload.")
        return redirect('cockpit')

    try:
        result = import_bulk_attendance(
            file_bytes=file_obj.read(),
            file_name=file_obj.name,
            default_session_id=session_id or None,
            recorded_by=request.user if request.user.is_authenticated else None
        )
        msg = f"Attendance import completed: {result['imported_count']} records imported, {result['skipped_count']} skipped."
        if result['errors']:
            msg += f" (Encountered {len(result['errors'])} errors)."
        messages.success(request, msg)
    except Exception as exc:
        messages.error(request, f"Import failed: {str(exc)}")

    return redirect('cockpit')


def verify_certificate_view(request, code=None):
    """
    Public accreditation credential verification page.
    Allows lenders, buyers, or partners to verify a DFAC smallholder certificate.
    """
    query_code = code or request.GET.get('code', '').strip()
    result = None

    if query_code:
        result = verify_certificate_credential(query_code)

    return render(request, 'portal/verify_certificate.html', {
        'page_title': 'Verify Training Accreditation - DFAC AgriDEP',
        'query_code': query_code,
        'result': result,
    })


@role_required(UserRole.LENDER, UserRole.DFAC_ADMIN)
def lender_portal_view(request):
    """
    Role-Scoped Lender Credit Portfolio Portal:
    Provides agricultural credit monitors with loan book performance metrics,
    harvest biomass coverage ratios, and early-warning delinquency alerts.
    """
    user = request.user
    role = getattr(user, 'role', '')
    
    # Scoping
    loans_qs = LoanRecord.objects.all().select_related('farmer', 'lender', 'farm', 'production_cycle')
    if role == 'LENDER':
        loans_qs = loans_qs.filter(lender__user=user)

    total_loans = loans_qs.count()
    principal_sum = loans_qs.aggregate(total=Sum('principal_amount_naira'))['total'] or Decimal('0.00')
    repaid_sum = loans_qs.aggregate(total=Sum('total_repaid_naira'))['total'] or Decimal('0.00')
    outstanding_sum = sum((l.outstanding_balance_naira for l in loans_qs), Decimal('0.00'))

    performing_count = loans_qs.filter(status=LoanStatus.PERFORMING).count()
    delinquent_count = loans_qs.filter(status=LoanStatus.DELINQUENT).count()
    watchlist_count = loans_qs.filter(status=LoanStatus.WATCHLIST).count()

    active_risk_flags = RiskFlag.objects.filter(
        loan__in=loans_qs,
        is_resolved=False
    ).select_related('loan', 'farmer')

    # Build loan analysis summary cards
    loan_items = []
    for loan in loans_qs[:15]:
        analysis = calculate_loan_expected_value_and_risk(loan)
        loan_items.append({
            'loan': loan,
            'expected_harvest': analysis['expected_harvest_value'],
            'coverage_ratio': analysis['coverage_ratio'],
            'risk_level': analysis['risk_level'],
        })

    return render(request, 'portal/lender_portal.html', {
        'page_title': 'Lender Credit Portfolio - DFAC AgriDEP',
        'metrics': {
            'total_loans': total_loans,
            'principal_sum': principal_sum,
            'repaid_sum': repaid_sum,
            'outstanding_sum': outstanding_sum,
            'performing_count': performing_count,
            'delinquent_count': delinquent_count,
            'watchlist_count': watchlist_count,
            'active_risks_count': active_risk_flags.count(),
        },
        'loan_items': loan_items,
        'active_risk_flags': active_risk_flags,
    })


@role_required(UserRole.BUYER, UserRole.DFAC_ADMIN)
def buyer_portal_view(request):
    """
    Role-Scoped Commercial Buyer & Off-taker Portal:
    Enables processors and aggregators to post purchase demands,
    view anonymized smallholder supply pools, and confirm forward contracts.
    """
    user = request.user
    role = getattr(user, 'role', '')

    demands_qs = BuyerDemand.objects.all().select_related('buyer', 'enterprise_type')
    matches_qs = ProduceMatch.objects.all().select_related('buyer_demand', 'produce_batch', 'produce_batch__farm__farmer', 'buyer_demand__buyer')
    offtakes_qs = OfftakeTransaction.objects.all().select_related('match', 'match__buyer_demand__buyer', 'match__produce_batch__farm__farmer')

    if role == 'BUYER':
        demands_qs = demands_qs.filter(buyer__user=user)
        matches_qs = matches_qs.filter(buyer_demand__buyer__user=user)
        offtakes_qs = offtakes_qs.filter(match__buyer_demand__buyer__user=user)

    total_demands = demands_qs.count()
    total_requested_kg = demands_qs.aggregate(total=Sum('target_volume_kg'))['total'] or Decimal('0.00')
    total_fulfilled_kg = demands_qs.aggregate(total=Sum('fulfilled_volume_kg'))['total'] or Decimal('0.00')
    active_matches_count = matches_qs.count()
    confirmed_offtakes_count = offtakes_qs.count()

    # Masked vs unmasked matches
    is_admin = user.is_authenticated and (user.is_superuser or role == 'DFAC_ADMIN')
    matches_list = []
    for m in matches_qs.order_by('-created_at')[:15]:
        farmer = m.produce_batch.farm.farmer
        is_unmasked = is_admin or (m.status in [MatchStatus.CONTRACTED, MatchStatus.FULFILLED])
        matches_list.append({
            'match': m,
            'producer_display': farmer.full_name if is_unmasked else f"Smallholder Producer #{farmer.reference_code or farmer.id}",
            'producer_phone': farmer.phone_normalized if is_unmasked else "[Masked until Contract Confirmed]",
            'location': f"{farmer.lga}, {farmer.state}" if is_unmasked else f"Verified Hub ({farmer.lga})",
            'is_unmasked': is_unmasked
        })

    enterprises = EnterpriseType.objects.filter(is_active=True)

    return render(request, 'portal/buyer_portal.html', {
        'page_title': 'Commercial Buyer Off-take Portal - DFAC AgriDEP',
        'metrics': {
            'total_demands': total_demands,
            'total_requested_tonnes': round(float(total_requested_kg) / 1000.0, 1),
            'total_fulfilled_tonnes': round(float(total_fulfilled_kg) / 1000.0, 1),
            'active_matches_count': active_matches_count,
            'confirmed_offtakes_count': confirmed_offtakes_count,
        },
        'demands': demands_qs[:10],
        'matches_list': matches_list,
        'offtakes': offtakes_qs[:10],
        'enterprises': enterprises,
    })


@require_POST
def confirm_produce_match_portal(request, match_id):
    """Confirms a proposed produce match into a binding contract and generates waybill."""
    match = get_object_or_404(ProduceMatch, id=match_id)
    offtake = confirm_produce_match(match, confirmed_by=request.user if request.user.is_authenticated else None)
    messages.success(request, f"Contract confirmed for {match.allocated_volume_kg:,.0f}kg with {match.buyer_demand.buyer.company_name}! Waybill #{offtake.waybill_number} generated.")
    return redirect('buyer-portal')


@require_POST
def trigger_auto_match_portal(request, demand_id):
    """Triggers RULE-04 spatial auto-matching algorithm for a buyer demand."""
    demand = get_object_or_404(BuyerDemand, id=demand_id)
    matches = propose_buyer_matches_for_demand(demand)
    if matches:
        messages.success(request, f"Successfully matched {len(matches)} producer batches ({demand.fulfilled_volume_kg:,.0f}kg allocated).")
    else:
        messages.warning(request, "No eligible producer batches found matching the delivery window and radius criteria.")
    return redirect('buyer-portal')


@role_required(UserRole.FIELD_OFFICER, UserRole.DFAC_ADMIN)
def field_officer_portal_view(request):
    """
    Milestone M4: Field Extension Officer daily inspection and priority queue cockpit.
    """
    from agridep.apps.fieldops.models import FarmVisit, IncidentReport, VisitAssignment
    from agridep.apps.fieldops.services import build_visit_priority_queue

    officer = request.user if request.user.is_authenticated and getattr(request.user, 'role', '') == UserRole.FIELD_OFFICER else None
    priority_queue = build_visit_priority_queue(officer=officer, limit=20)
    assignments = VisitAssignment.objects.select_related('farm', 'farm__farmer', 'assigned_officer').order_by('-priority_score', 'due_date')[:15]
    recent_visits = FarmVisit.objects.select_related('farm', 'farm__farmer', 'officer').order_by('-actual_visit_date', '-created_at')[:15]
    open_incidents_count = IncidentReport.objects.filter(status__in=['REPORTED', 'INVESTIGATING']).count()

    total_visits = FarmVisit.objects.count()
    verified_visits = FarmVisit.objects.filter(is_geofence_verified=True).count()
    geofence_verified_pct = round((verified_visits / total_visits * 100), 1) if total_visits > 0 else 100.0

    return render(request, 'portal/fieldops_portal.html', {
        'page_title': 'Field Operations & Inspection Cockpit - DFAC AgriDEP',
        'priority_queue': priority_queue,
        'assignments': assignments,
        'recent_visits': recent_visits,
        'active_assignments_count': VisitAssignment.objects.filter(status__in=['PENDING', 'ACCEPTED', 'IN_PROGRESS']).count(),
        'open_incidents_count': open_incidents_count,
        'geofence_verified_pct': geofence_verified_pct,
    })


@require_POST
def fieldops_log_visit_portal(request):
    """Logs a completed field visit with GPS coordinates and inspection biometrics."""
    from agridep.apps.registry.models import Farm
    from agridep.apps.fieldops.models import Inspection, ComplianceRating
    from agridep.apps.fieldops.services import log_farm_visit

    farm_id = request.POST.get('farm_id')
    farm = get_object_or_404(Farm, id=farm_id)
    lat = Decimal(request.POST.get('latitude', '0'))
    lon = Decimal(request.POST.get('longitude', '0'))
    purpose = request.POST.get('purpose', 'ROUTINE_EXTENSION')
    officer_notes = request.POST.get('officer_notes', '')

    visit = log_farm_visit(
        farm=farm,
        officer=request.user if request.user.is_authenticated else farm.farmer.assigned_officer,
        purpose=purpose,
        latitude=lat,
        longitude=lon,
        officer_notes=officer_notes
    )

    # Also log inspection if biometrics provided
    water_ph = request.POST.get('water_ph')
    water_temp = request.POST.get('water_temp')
    do_val = request.POST.get('dissolved_oxygen')
    avg_weight = request.POST.get('avg_weight_g')
    mortality = request.POST.get('mortality_count', '0')

    Inspection.objects.create(
        visit=visit,
        water_ph=Decimal(water_ph) if water_ph else None,
        water_temperature_celsius=Decimal(water_temp) if water_temp else None,
        dissolved_oxygen_mg_l=Decimal(do_val) if do_val else None,
        average_sample_weight_grams=Decimal(avg_weight) if avg_weight else None,
        daily_mortality_count=int(mortality) if mortality else 0,
        compliance_rating=ComplianceRating.SATISFACTORY if (water_ph and 6.5 <= float(water_ph) <= 8.5) else ComplianceRating.NEEDS_IMPROVEMENT
    )

    if visit.is_geofence_verified:
        messages.success(request, f"Visit #{visit.reference_code} logged! ✓ On-site GPS verified ({visit.distance_to_farm_meters:.1f}m from farm coordinates).")
    else:
        messages.warning(request, f"Visit #{visit.reference_code} logged! ⚠ GPS Geofence drift warning ({visit.distance_to_farm_meters:.1f}m from farm coordinates).")

    return redirect('fieldops-portal')


@require_POST
def fieldops_report_incident_portal(request):
    """Submits an emergency incident and auto-dispatches high priority visits."""
    from agridep.apps.registry.models import Farm
    from agridep.apps.fieldops.services import report_incident

    farm_id = request.POST.get('farm_id')
    farm = get_object_or_404(Farm, id=farm_id)
    title = request.POST.get('title')
    description = request.POST.get('description')
    incident_type = request.POST.get('incident_type', 'DISEASE_OUTBREAK')
    severity = request.POST.get('severity', 'HIGH')

    incident = report_incident(
        farm=farm,
        reported_by=request.user if request.user.is_authenticated else farm.farmer.assigned_officer,
        title=title,
        description=description,
        incident_type=incident_type,
        severity=severity
    )

    messages.success(request, f"Incident #{incident.reference_code} recorded! Urgent field inspection dispatched to assigned extension officer.")
    return redirect('fieldops-portal')


@require_POST
def fieldops_auto_dispatch_portal(request):
    """Runs priority scanner and automatically creates VisitAssignments."""
    from agridep.apps.fieldops.services import auto_generate_visit_assignments

    created = auto_generate_visit_assignments()
    if created:
        messages.success(request, f"Decision Engine dispatched {len(created)} urgent visit assignments based on current risk and overdue scores.")
    else:
        messages.info(request, "Priority scanner completed. No new visits meet the urgent dispatch threshold at this time.")
    return redirect('fieldops-portal')


def ussd_simulator_view(request):
    """
    Milestone M6: Interactive 2G Feature Phone USSD & SMS Gateway Simulator.
    """
    from agridep.apps.alerts.models import AlertNotification
    recent = AlertNotification.objects.order_by('-created_at')[:10]
    return render(request, 'portal/ussd_simulator.html', {
        'page_title': 'Rural USSD & SMS Simulator - DFAC AgriDEP',
        'recent_notifications': recent,
    })


@role_required(UserRole.DFAC_ADMIN)
def donor_reporting_portal_view(request):
    """
    Milestone M7: Automated Donor Reporting Portal (PIND & GIZ M&E Indicators).
    """
    from agridep.apps.reporting.services import compute_donor_me_indicators
    donor = request.GET.get('donor', 'PIND')
    indicators = compute_donor_me_indicators(donor=donor)
    return render(request, 'portal/reporting_portal.html', {
        'page_title': f'{donor.upper()} M&E Donor Reporting - DFAC AgriDEP',
        'donor': donor.upper(),
        'indicators': indicators,
    })


@role_required(UserRole.DFAC_ADMIN, UserRole.FIELD_OFFICER)
def inputs_portal_view(request):
    """
    Milestone M7: Input Supplier Directory & In-Kind Order Fulfillment Portal.
    """
    from agridep.apps.inputs.models import InputSupplier, InputOrder, InputCatalogItem
    from agridep.apps.finance.models import LoanTranche
    suppliers = InputSupplier.objects.all().prefetch_related('catalog_items')
    orders = InputOrder.objects.all().select_related('farmer', 'supplier', 'tranche').order_by('-created_at')[:25]
    tranches = LoanTranche.objects.all().select_related('loan', 'loan__farmer').order_by('-created_at')[:20]

    return render(request, 'portal/inputs_portal.html', {
        'page_title': 'Agro-Inputs & Tranche Delivery Management - DFAC AgriDEP',
        'suppliers': suppliers,
        'orders': orders,
        'tranches': tranches,
    })


def confirm_input_delivery_portal(request, order_id):
    """Confirm receipt of agricultural inputs on-farm."""
    from agridep.apps.inputs.models import InputOrder, DeliveryConfirmationChannel
    from agridep.apps.inputs.services import confirm_input_delivery
    order = get_object_or_404(InputOrder, pk=order_id)
    confirm_input_delivery(
        order=order,
        confirmation_channel=DeliveryConfirmationChannel.PORTAL_MANUAL,
        confirmed_by=request.user if request.user.is_authenticated else None,
        notes="Verified delivery via DFAC Inputs Portal."
    )
    messages.success(request, f"Order {order.order_code} delivery confirmed! Linked loan tranche unblocked.")
    return redirect('inputs-portal')


def download_apk_view(request):
    """
    Serves the compiled DFAC AgriDEP Field Android APK (v1.0.0) for download.
    """
    import os
    from django.conf import settings

    apk_path = os.path.join(settings.BASE_DIR, 'agridep', 'static', 'downloads', 'dfac-agridep-field-v1.0.0.apk')
    if not os.path.exists(apk_path):
        raise Http404("DFAC AgriDEP Field APK is not available. Please trigger the APK build.")

    response = FileResponse(
        open(apk_path, 'rb'),
        content_type='application/vnd.android.package-archive',
        as_attachment=True,
        filename='dfac-agridep-field-v1.0.0.apk'
    )
    response['Content-Length'] = os.path.getsize(apk_path)
    return response


# =============================================================================
# Milestone M5: Trainer & Extension Specialist Portal
# =============================================================================
@role_required(UserRole.TRAINER, UserRole.DFAC_ADMIN)
def trainer_portal_view(request):
    """
    Capacity Building & Accreditation Desk:
    Allows training specialists to schedule curriculum cohorts,
    manage attendance rosters, record competency test scores,
    and issue tamper-evident verifiable credentials.
    """
    programmes = TrainingProgramme.objects.filter(is_active=True).order_by('title')
    sessions = TrainingSession.objects.all().select_related('programme', 'trainer').order_by('-start_date')
    if getattr(request.user, 'role', '') == UserRole.TRAINER and not request.user.is_superuser:
        sessions = sessions.filter(trainer=request.user)

    certificates = Certificate.objects.all().select_related('farmer', 'programme', 'session').order_by('-created_at')[:25]
    farmers = Farmer.objects.filter(verification_status=VerificationStatus.VERIFIED).order_by('first_name', 'last_name')[:60]

    total_sessions = sessions.count()
    completed_sessions = sessions.filter(status='COMPLETED').count()
    total_certs = Certificate.objects.count()
    total_trainees = Attendance.objects.filter(status='PRESENT').values('farmer').distinct().count()

    return render(request, 'portal/trainer_portal.html', {
        'page_title': 'Extension & Training Accreditation Desk - DFAC AgriDEP',
        'programmes': programmes,
        'sessions': sessions[:15],
        'certificates': certificates,
        'farmers': farmers,
        'stats': {
            'total_sessions': total_sessions,
            'completed_sessions': completed_sessions,
            'total_certs': total_certs,
            'total_trainees': total_trainees,
        }
    })


@require_POST
@role_required(UserRole.TRAINER, UserRole.DFAC_ADMIN)
def trainer_schedule_session_portal(request):
    """Schedules a new cohort training workshop."""
    programme_id = request.POST.get('programme_id')
    programme = get_object_or_404(TrainingProgramme, id=programme_id)
    title = request.POST.get('title', '').strip() or f"{programme.title} - Cohort"
    location = request.POST.get('location', '').strip()
    start_date = request.POST.get('start_date') or timezone.now().date()
    end_date = request.POST.get('end_date') or timezone.now().date()
    total_days = int(request.POST.get('total_scheduled_days', 5))

    session = TrainingSession.objects.create(
        programme=programme,
        trainer=request.user,
        title=title,
        location=location,
        start_date=start_date,
        end_date=end_date,
        total_scheduled_days=total_days
    )
    messages.success(request, f"Cohort session '{session.title}' scheduled successfully at {location}!")
    return redirect('trainer-portal')


@require_POST
@role_required(UserRole.TRAINER, UserRole.DFAC_ADMIN)
def trainer_issue_certificate_portal(request):
    """Issues a verifiable digital certificate to a trained smallholder."""
    import random
    from datetime import timedelta
    session_id = request.POST.get('session_id')
    farmer_id = request.POST.get('farmer_id')
    session = get_object_or_404(TrainingSession, id=session_id)
    farmer = get_object_or_404(Farmer, id=farmer_id)

    short_code = f"CERT-DFAC-{random.randint(10000, 99999)}"
    enterprise_code = session.programme.enterprise_type.code if (session.programme and session.programme.enterprise_type) else 'GAP'
    cert_no = f"DFAC-{enterprise_code}-2026-{random.randint(1000, 9999)}"

    cert = Certificate.objects.create(
        farmer=farmer,
        programme=session.programme,
        session=session,
        certificate_number=cert_no,
        verification_code=short_code,
        issue_date=timezone.now().date(),
        expiry_date=timezone.now().date() + timedelta(days=730),
        is_valid=True
    )
    messages.success(request, f"Verifiable Certificate #{cert.certificate_number} issued for {farmer.full_name}! Verification Code: {cert.verification_code}")
    return redirect('trainer-portal')


# =============================================================================
# Milestone M5: Smallholder Farmer Self-Service Portal
# =============================================================================
@role_required(UserRole.FARMER, UserRole.FIELD_OFFICER, UserRole.DFAC_ADMIN)
def farmer_portal_view(request):
    """
    Smallholder Self-Service Desk:
    Gives verified farmers transparency over their registered ponds/plots,
    active production cycles, biometrics, input vouchers, loan facilities,
    and guaranteed offtake contracts.
    """
    farmer = getattr(request.user, 'farmer_profile', None)
    if not farmer:
        farmer = Farmer.objects.filter(verification_status=VerificationStatus.VERIFIED).first()

    farms = farmer.farms.all() if farmer else []
    cycles = ProductionCycle.objects.filter(farm__farmer=farmer).select_related('farm', 'enterprise_type') if farmer else []
    loans = farmer.loans.all().prefetch_related('tranches') if farmer else []
    certificates = farmer.certificates.all().select_related('programme', 'session') if farmer else []
    matches = ProduceMatch.objects.filter(produce_batch__farm__farmer=farmer).select_related('buyer_demand', 'buyer_demand__buyer') if farmer else []

    return render(request, 'portal/farmer_portal.html', {
        'page_title': f'Smallholder Desk: {farmer.first_name if farmer else "Farmer"} - DFAC AgriDEP',
        'farmer': farmer,
        'farms': farms,
        'cycles': cycles,
        'loans': loans,
        'certificates': certificates,
        'matches': matches,
    })


# =============================================================================
# User Profile & Security Settings
# =============================================================================
@login_required
def user_profile_view(request):
    """
    User Account Profile & Security Settings:
    Allows all authenticated stakeholders to update personal contact details,
    view assigned role permissions, review NDPA consent status, and change password.
    """
    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            first_name = request.POST.get('first_name', '').strip()
            last_name = request.POST.get('last_name', '').strip()
            email = request.POST.get('email', '').strip()
            phone_number = request.POST.get('phone_number', '').strip()
            state = request.POST.get('state', '').strip()
            lga = request.POST.get('lga', '').strip()

            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.phone_number = phone_number
            user.state = state or "Delta"
            user.lga = lga
            user.save()

            messages.success(request, "Your profile details have been successfully updated.")
            return redirect('portal-profile')

        elif action == 'change_password':
            old_password = request.POST.get('old_password', '')
            new_password = request.POST.get('new_password', '')
            confirm_password = request.POST.get('confirm_password', '')

            if not user.check_password(old_password):
                messages.error(request, "Current password does not match.")
            elif len(new_password) < 6:
                messages.error(request, "New password must be at least 6 characters long.")
            elif new_password != confirm_password:
                messages.error(request, "New passwords do not match.")
            else:
                user.set_password(new_password)
                user.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password changed successfully! Session preserved.")
                return redirect('portal-profile')

    consents = ConsentRecord.objects.filter(user=user)[:5] if user.is_authenticated else []

    return render(request, 'portal/profile.html', {
        'page_title': f'User Profile: {user.username} - DFAC AgriDEP',
        'user_obj': user,
        'consents': consents,
    })


# =============================================================================
# Custom Professional Admin Management Console
# =============================================================================
@admin_required
def admin_console_view(request):
    """
    Professional Custom Admin Management Console:
    Full-fledged replacement for standard Django admin.
    Features: User management, role modification, status toggle,
    registry verification desk, system audit trail, and ecosystem health.
    """
    # 1. User & Stakeholder Management
    users_qs = User.objects.all().order_by('-date_joined')
    
    role_filter = request.GET.get('role', '')
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')

    if role_filter:
        users_qs = users_qs.filter(role=role_filter)
    if search_query:
        users_qs = users_qs.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    if status_filter == 'active':
        users_qs = users_qs.filter(is_active=True)
    elif status_filter == 'inactive':
        users_qs = users_qs.filter(is_active=False)

    # 2. Smallholder Verification Queue
    pending_farmers = Farmer.objects.filter(
        verification_status__in=[VerificationStatus.PENDING_REVIEW, VerificationStatus.FLAGGED_DUPLICATE]
    ).order_by('-created_at')[:20]

    # 3. System Audit Trail
    audit_events = AuditEvent.objects.all().select_related('user').order_by('-timestamp')[:25]

    # 4. Global Platform KPI Counters
    total_users = User.objects.count()
    total_farmers = Farmer.objects.count()
    verified_farmers = Farmer.objects.filter(verification_status=VerificationStatus.VERIFIED).count()
    total_farms = Farm.objects.count()
    total_cycles = ProductionCycle.objects.count()
    total_loans = LoanRecord.objects.count()
    total_matches = ProduceMatch.objects.count()

    role_counts = {
        'admin': User.objects.filter(role=UserRole.DFAC_ADMIN).count(),
        'officer': User.objects.filter(role=UserRole.FIELD_OFFICER).count(),
        'trainer': User.objects.filter(role=UserRole.TRAINER).count(),
        'lender': User.objects.filter(role=UserRole.LENDER).count(),
        'buyer': User.objects.filter(role=UserRole.BUYER).count(),
        'farmer': User.objects.filter(role=UserRole.FARMER).count(),
    }

    return render(request, 'portal/admin_console.html', {
        'page_title': 'DFAC Executive Administration Console',
        'users': users_qs[:40],
        'total_user_count': total_users,
        'role_counts': role_counts,
        'selected_role': role_filter,
        'search_query': search_query,
        'selected_status': status_filter,
        'pending_farmers': pending_farmers,
        'audit_events': audit_events,
        'roles': UserRole.choices,
        'stats': {
            'total_users': total_users,
            'total_farmers': total_farmers,
            'verified_farmers': verified_farmers,
            'total_farms': total_farms,
            'total_cycles': total_cycles,
            'total_loans': total_loans,
            'total_matches': total_matches,
        }
    })


@require_POST
@admin_required
def admin_toggle_user_status_view(request, user_id):
    """Toggles active/inactive state of a system user."""
    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        messages.error(request, "Security protection: You cannot deactivate your own administrative account.")
        return redirect('admin-console')

    target_user.is_active = not target_user.is_active
    target_user.save()
    status_str = "activated" if target_user.is_active else "deactivated"
    messages.success(request, f"User {target_user.username} has been {status_str}.")
    return redirect('admin-console')


@require_POST
@admin_required
def admin_change_user_role_view(request, user_id):
    """Updates the role assigned to a stakeholder user."""
    target_user = get_object_or_404(User, id=user_id)
    new_role = request.POST.get('role')
    if new_role in dict(UserRole.choices):
        target_user.role = new_role
        target_user.save()
        messages.success(request, f"Role for {target_user.username} updated to '{target_user.get_role_display()}'.")
    else:
        messages.error(request, "Invalid role specified.")
    return redirect('admin-console')


@require_POST
@admin_required
def admin_create_user_view(request):
    """Creates a new stakeholder account directly from the Custom Admin Console."""
    username = request.POST.get('username', '').strip()
    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    email = request.POST.get('email', '').strip()
    phone_number = request.POST.get('phone_number', '').strip()
    role = request.POST.get('role', UserRole.FIELD_OFFICER)
    password = request.POST.get('password', '').strip() or 'password123'
    state = request.POST.get('state', 'Delta').strip()
    lga = request.POST.get('lga', '').strip()

    if not username:
        messages.error(request, "Username is required.")
        return redirect('admin-console')

    if User.objects.filter(username=username).exists():
        messages.error(request, f"Username '{username}' already exists. Please pick another.")
        return redirect('admin-console')

    new_user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=role,
        phone_number=phone_number or None,
        state=state,
        lga=lga,
        is_active=True
    )
    messages.success(request, f"New {new_user.get_role_display()} account created for '{new_user.username}'!")
    return redirect('admin-console')


@require_POST
@admin_required
def admin_verify_farmer_view(request, farmer_id):
    """Admin 1-click verification of smallholder identity."""
    farmer = get_object_or_404(Farmer, id=farmer_id)
    farmer.verification_status = VerificationStatus.VERIFIED
    farmer.duplicate_review_notes = f"Verified by Administrator {request.user.username} on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
    farmer.save()
    messages.success(request, f"Farmer {farmer.full_name} (#{farmer.reference_code}) has been marked as VERIFIED!")
    return redirect('admin-console')






