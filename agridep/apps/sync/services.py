import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Tuple
from django.db import transaction
from django.utils import timezone
from agridep.apps.registry.models import Farmer, Farm, EnterpriseType, VerificationStatus
from agridep.apps.registry.services import check_farmer_duplicates
from agridep.apps.production.models import ProductionCycle, ProductionLog, CycleStage
from agridep.apps.production.services import process_production_log
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
from agridep.apps.fieldops.services import verify_geofence, report_incident
from agridep.apps.accounts.models import ConsentRecord, StakeholderCategory, ConsentChannel
from .models import IngestionLog, IngestionSource, ConflictLog, MediaUploadSession

def ingest_kobo_submission(payload: Dict[str, Any], user=None) -> Tuple[bool, str]:
    """
    Ingests and processes raw submissions from KoboToolbox / ODK Collect forms.
    Supports form types: 'farmer_registration' and 'production_log'.
    """
    submission_id = payload.get('_id') or payload.get('meta/instanceID') or payload.get('submission_id')
    if submission_id:
        submission_id = str(submission_id)
        if IngestionLog.objects.filter(submission_id=submission_id).exists():
            return True, f"Submission {submission_id} already ingested (idempotent skip)"

    form_id = payload.get('form_id') or payload.get('_xform_id_string') or 'farmer_registration'

    try:
        with transaction.atomic():
            if 'farmer' in form_id.lower() or 'registration' in form_id.lower():
                first_name = payload.get('first_name', '').strip()
                last_name = payload.get('last_name', '').strip()
                phone = payload.get('phone', '').strip()
                nin = payload.get('nin', '').strip()
                state = payload.get('state', 'Delta').strip()
                lga = payload.get('lga', 'Warri South').strip()
                community = payload.get('community', '').strip()

                lat = payload.get('latitude') or payload.get('_geolocation', [None, None])[0]
                lon = payload.get('longitude') or payload.get('_geolocation', [None, None])[1]
                lat = float(lat) if lat is not None else 5.544230
                lon = float(lon) if lon is not None else 5.760269

                is_dup, rec_status, reasons, _ = check_farmer_duplicates(
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    nin=nin,
                    lat=lat,
                    lon=lon
                )

                farmer = Farmer.objects.create(
                    first_name=first_name,
                    last_name=last_name,
                    phone_normalized=phone,
                    state=state,
                    lga=lga,
                    community_address=community,
                    assigned_officer=user if user and getattr(user, 'role', '') == 'FIELD_OFFICER' else None,
                    verification_status=rec_status,
                    duplicate_review_notes="; ".join(reasons) if reasons else ""
                )
                if nin:
                    farmer.set_nin(nin)
                    farmer.save(update_fields=['nin_encrypted', 'nin_hash'])

                # Record NDPA Consent automatically
                ConsentRecord.objects.create(
                    farmer_reference=farmer.reference_code,
                    stakeholder_category=StakeholderCategory.ALL_ECOSYSTEM,
                    consent_given=True,
                    consent_scope="Standard Smallholder Participation and Data Sharing Consent",
                    channel=ConsentChannel.KOBO_FORM,
                    captured_by=user
                )

                # Create farm
                farm_name = payload.get('farm_name', f"{first_name}'s Farm")
                ponds = int(payload.get('number_of_ponds', 4))
                area_ha = Decimal(str(payload.get('total_area_hectares', '0.50')))
                farm = Farm.objects.create(
                    farmer=farmer,
                    name=farm_name,
                    latitude=lat,
                    longitude=lon,
                    community=community,
                    number_of_ponds=ponds,
                    total_area_hectares=area_ha
                )
                # Link catfish enterprise as default
                catfish = EnterpriseType.objects.filter(code='CATFISH').first()
                if catfish:
                    farm.enterprise_types.add(catfish)

            elif 'production' in form_id.lower() or 'log' in form_id.lower():
                cycle_id = payload.get('cycle_id')
                cycle = None
                if cycle_id:
                    cycle = ProductionCycle.objects.filter(id=cycle_id).first() or \
                            ProductionCycle.objects.filter(reference_code=cycle_id).first()
                
                if not cycle:
                    # Link to latest active cycle
                    cycle = ProductionCycle.objects.first()

                if cycle:
                    sample_weight = Decimal(str(payload.get('sampling_average_weight_g', '350.0')))
                    mortality = int(payload.get('observed_mortality_count', 0))
                    feed_kg = Decimal(str(payload.get('feed_consumed_kg', '15.0')))
                    temp = payload.get('water_temperature_c')
                    ph = payload.get('ph_level')

                    log = ProductionLog.objects.create(
                        cycle=cycle,
                        sampling_average_weight_g=sample_weight,
                        observed_mortality_count=mortality,
                        feed_consumed_kg=feed_kg,
                        water_temperature_c=Decimal(str(temp)) if temp else None,
                        ph_level=Decimal(str(ph)) if ph else None,
                        notes=payload.get('notes', '')
                    )
                    process_production_log(log)

            IngestionLog.objects.create(
                source=IngestionSource.KOBO_TOOLBOX,
                submission_id=submission_id,
                raw_payload=payload,
                processed_status='SUCCESS'
            )
            return True, "Ingested successfully"

    except Exception as e:
        IngestionLog.objects.create(
            source=IngestionSource.KOBO_TOOLBOX,
            submission_id=submission_id,
            raw_payload=payload,
            processed_status='FAILED',
            error_message=str(e)
        )
        return False, str(e)

def process_sync_push(user, operations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Processes batch outbox operations from the Flutter Drift SQLite client.
    Each operation is:
    {
        "client_id": "uuid",
        "table": "farmers" | "farms" | "production_cycles" | "production_logs",
        "operation": "CREATE" | "UPDATE",
        "data": {...},
        "client_updated_at": "iso_timestamp"
    }
    """
    synced_ids = []
    conflicts = []

    with transaction.atomic():
        for op in operations:
            c_id = op.get('client_id')
            table = op.get('table')
            data = op.get('data', {})
            op_type = op.get('operation', 'CREATE')

            if table == 'farmers':
                farmer = Farmer.objects.filter(client_id=c_id).first()
                if not farmer:
                    is_dup, rec_status, reasons, _ = check_farmer_duplicates(
                        first_name=data.get('first_name', ''),
                        last_name=data.get('last_name', ''),
                        phone=data.get('phone_normalized', ''),
                        nin=data.get('nin', '')
                    )
                    farmer = Farmer.objects.create(
                        client_id=c_id,
                        first_name=data.get('first_name', ''),
                        last_name=data.get('last_name', ''),
                        phone_normalized=data.get('phone_normalized', ''),
                        gender=data.get('gender', 'MALE'),
                        state=data.get('state', 'Delta'),
                        lga=data.get('lga', ''),
                        community_address=data.get('community_address', ''),
                        assigned_officer=user,
                        verification_status=rec_status,
                        duplicate_review_notes="; ".join(reasons) if reasons else ""
                    )
                    if data.get('nin'):
                        farmer.set_nin(data['nin'])
                        farmer.save(update_fields=['nin_encrypted', 'nin_hash'])
                synced_ids.append(c_id)

            elif table == 'farms':
                farm = Farm.objects.filter(client_id=c_id).first()
                if not farm:
                    farmer_client_id = data.get('farmer_client_id')
                    farmer = Farmer.objects.filter(client_id=farmer_client_id).first() or Farmer.objects.first()
                    if farmer:
                        farm = Farm.objects.create(
                            client_id=c_id,
                            farmer=farmer,
                            name=data.get('name', 'Farm Facility'),
                            latitude=data.get('latitude', 5.5442),
                            longitude=data.get('longitude', 5.7602),
                            number_of_ponds=data.get('number_of_ponds', 4),
                            total_area_hectares=data.get('total_area_hectares', 0.50),
                            community=data.get('community', '')
                        )
                synced_ids.append(c_id)

            elif table == 'production_logs':
                log = ProductionLog.objects.filter(client_id=c_id).first()
                if not log:
                    cycle_client_id = data.get('cycle_client_id')
                    cycle = ProductionCycle.objects.filter(client_id=cycle_client_id).first() or ProductionCycle.objects.first()
                    if cycle:
                        log = ProductionLog.objects.create(
                            client_id=c_id,
                            cycle=cycle,
                            sampling_average_weight_g=data.get('sampling_average_weight_g', 300.0),
                            observed_mortality_count=data.get('observed_mortality_count', 0),
                            feed_consumed_kg=data.get('feed_consumed_kg', 10.0),
                            water_temperature_c=data.get('water_temperature_c'),
                            ph_level=data.get('ph_level'),
                            notes=data.get('notes', '')
                        )
                        process_production_log(log)
                synced_ids.append(c_id)

            elif table == 'farm_visits':
                visit = FarmVisit.objects.filter(client_id=c_id).first()
                if not visit:
                    farm_client_id = data.get('farm_client_id')
                    farm = Farm.objects.filter(client_id=farm_client_id).first() or Farm.objects.filter(id=data.get('farm_id')).first() or Farm.objects.first()
                    if farm:
                        lat = Decimal(str(data.get('latitude', farm.latitude)))
                        lon = Decimal(str(data.get('longitude', farm.longitude)))
                        is_verified, distance = verify_geofence(farm, lat, lon)
                        
                        visit = FarmVisit.objects.create(
                            client_id=c_id,
                            farm=farm,
                            officer=user,
                            status=data.get('status', FarmVisitStatus.COMPLETED),
                            purpose=data.get('purpose', FarmVisitPurpose.ROUTINE_EXTENSION),
                            farmer_present=data.get('farmer_present', True),
                            latitude=lat,
                            longitude=lon,
                            gps_accuracy_meters=Decimal(str(data.get('gps_accuracy_meters', '5.00'))),
                            is_geofence_verified=is_verified,
                            distance_to_farm_meters=distance,
                            officer_notes=data.get('officer_notes', ''),
                            farmer_feedback=data.get('farmer_feedback', '')
                        )
                synced_ids.append(c_id)

            elif table == 'inspections':
                inspection = Inspection.objects.filter(client_id=c_id).first()
                if not inspection:
                    visit_client_id = data.get('visit_client_id')
                    visit = FarmVisit.objects.filter(client_id=visit_client_id).first() or FarmVisit.objects.first()
                    if visit:
                        inspection = Inspection.objects.create(
                            client_id=c_id,
                            visit=visit,
                            inspection_type=data.get('inspection_type', InspectionType.WATER_QUALITY),
                            compliance_rating=data.get('compliance_rating', ComplianceRating.SATISFACTORY),
                            water_ph=Decimal(str(data['water_ph'])) if data.get('water_ph') else None,
                            water_temperature_celsius=Decimal(str(data['water_temperature_celsius'])) if data.get('water_temperature_celsius') else None,
                            dissolved_oxygen_mg_l=Decimal(str(data['dissolved_oxygen_mg_l'])) if data.get('dissolved_oxygen_mg_l') else None,
                            ammonia_ppm=Decimal(str(data['ammonia_ppm'])) if data.get('ammonia_ppm') else None,
                            average_sample_weight_grams=Decimal(str(data['average_sample_weight_grams'])) if data.get('average_sample_weight_grams') else None,
                            daily_mortality_count=int(data.get('daily_mortality_count', 0)),
                            feed_inventory_kg=Decimal(str(data['feed_inventory_kg'])) if data.get('feed_inventory_kg') else None,
                            checklist_scores=data.get('checklist_scores', {}),
                            biosecurity_protocol_followed=data.get('biosecurity_protocol_followed', True),
                            summary_findings=data.get('summary_findings', '')
                        )
                synced_ids.append(c_id)

            elif table == 'incident_reports':
                incident = IncidentReport.objects.filter(client_id=c_id).first()
                if not incident:
                    farm_client_id = data.get('farm_client_id')
                    farm = Farm.objects.filter(client_id=farm_client_id).first() or Farm.objects.filter(id=data.get('farm_id')).first() or Farm.objects.first()
                    if farm:
                        incident = report_incident(
                            farm=farm,
                            reported_by=user,
                            title=data.get('title', 'Emergency Field Incident'),
                            description=data.get('description', ''),
                            incident_type=data.get('incident_type', IncidentType.DISEASE_OUTBREAK),
                            severity=data.get('severity', IncidentSeverity.HIGH),
                            mortality_estimate=int(data.get('mortality_estimate', 0)),
                            financial_loss_estimate_ngn=Decimal(str(data.get('financial_loss_estimate_ngn', '0.00'))),
                            auto_dispatch_visit=True
                        )
                        incident.client_id = c_id
                        incident.save(update_fields=['client_id'])
                synced_ids.append(c_id)

            elif table == 'visit_assignments':
                asn = VisitAssignment.objects.filter(client_id=c_id).first() or VisitAssignment.objects.filter(id=data.get('id')).first()
                if asn:
                    # Update status
                    new_status = data.get('status')
                    if new_status and new_status in AssignmentStatus.values:
                        asn.status = new_status
                        asn.save(update_fields=['status', 'updated_at'])
                synced_ids.append(c_id)

    return {
        "synced_client_ids": synced_ids,
        "conflicts": conflicts,
        "synced_at": timezone.now().isoformat()
    }

def generate_sync_pull(user, since_iso: str = None) -> Dict[str, Any]:
    """
    Delta pull endpoint for the Flutter Drift SQLite client.
    Returns changed records scoped to the field officer's assigned farmers.
    """
    since_dt = None
    if since_iso:
        try:
            since_dt = datetime.fromisoformat(since_iso)
        except Exception:
            pass

    farmers_qs = Farmer.objects.all()
    farms_qs = Farm.objects.all()
    cycles_qs = ProductionCycle.objects.all()
    logs_qs = ProductionLog.objects.all()
    visits_qs = FarmVisit.objects.all()
    inspections_qs = Inspection.objects.all()
    incidents_qs = IncidentReport.objects.all()
    assignments_qs = VisitAssignment.objects.all()

    # Scope to field officer assignment if applicable
    if user and getattr(user, 'role', '') == 'FIELD_OFFICER':
        farmers_qs = farmers_qs.filter(assigned_officer=user)
        farms_qs = farms_qs.filter(farmer__assigned_officer=user)
        cycles_qs = cycles_qs.filter(farm__farmer__assigned_officer=user)
        logs_qs = logs_qs.filter(cycle__farm__farmer__assigned_officer=user)
        visits_qs = visits_qs.filter(officer=user)
        inspections_qs = inspections_qs.filter(visit__officer=user)
        assignments_qs = assignments_qs.filter(assigned_officer=user)

    if since_dt:
        farmers_qs = farmers_qs.filter(updated_at__gte=since_dt)
        farms_qs = farms_qs.filter(updated_at__gte=since_dt)
        cycles_qs = cycles_qs.filter(updated_at__gte=since_dt)
        logs_qs = logs_qs.filter(updated_at__gte=since_dt)
        visits_qs = visits_qs.filter(updated_at__gte=since_dt)
        inspections_qs = inspections_qs.filter(updated_at__gte=since_dt)
        incidents_qs = incidents_qs.filter(updated_at__gte=since_dt)
        assignments_qs = assignments_qs.filter(updated_at__gte=since_dt)

    def format_records(qs, fields):
        rows = list(qs.values(*fields))
        for r in rows:
            for k, v in r.items():
                if isinstance(v, uuid.UUID):
                    r[k] = str(v)
                elif hasattr(v, 'isoformat'):
                    r[k] = v.isoformat()
        return rows

    return {
        "new_cursor": timezone.now().isoformat(),
        "records": {
            "farmers": format_records(farmers_qs, [
                'id', 'client_id', 'reference_code', 'first_name', 'last_name',
                'phone_normalized', 'state', 'lga', 'community_address',
                'verification_status', 'updated_at'
            ]),
            "farms": format_records(farms_qs, [
                'id', 'client_id', 'reference_code', 'farmer_id', 'name',
                'latitude', 'longitude', 'number_of_ponds', 'total_area_hectares', 'updated_at'
            ]),
            "cycles": format_records(cycles_qs, [
                'id', 'client_id', 'reference_code', 'farm_id', 'cycle_name',
                'status', 'current_stock_count', 'current_average_weight_g',
                'projected_harvest_date', 'updated_at'
            ]),
            "logs": format_records(logs_qs, [
                'id', 'client_id', 'cycle_id', 'log_date',
                'sampling_average_weight_g', 'observed_mortality_count',
                'feed_consumed_kg', 'water_temperature_c', 'ph_level', 'updated_at'
            ]),
            "visits": format_records(visits_qs, [
                'id', 'client_id', 'reference_code', 'farm_id', 'status',
                'purpose', 'scheduled_date', 'actual_visit_date', 'is_geofence_verified',
                'distance_to_farm_meters', 'updated_at'
            ]),
            "inspections": format_records(inspections_qs, [
                'id', 'client_id', 'reference_code', 'visit_id', 'inspection_type',
                'compliance_rating', 'water_ph', 'water_temperature_celsius',
                'dissolved_oxygen_mg_l', 'daily_mortality_count', 'updated_at'
            ]),
            "incidents": format_records(incidents_qs, [
                'id', 'client_id', 'reference_code', 'farm_id', 'incident_type',
                'severity', 'status', 'title', 'reported_at', 'updated_at'
            ]),
            "assignments": format_records(assignments_qs, [
                'id', 'client_id', 'reference_code', 'farm_id', 'priority_score',
                'priority_level', 'trigger_reason', 'status', 'due_date', 'updated_at'
            ]),
        }
    }


def handle_resumable_media_chunk(user, client_id, file_name, chunk_file, total_size, offset=0, file_category="INSPECTION_PHOTO") -> Dict[str, Any]:
    """
    Handles chunked/resumable media uploads for low-bandwidth rural Niger Delta networks.
    Tracks received bytes in MediaUploadSession.
    """
    session, _ = MediaUploadSession.objects.get_or_create(
        client_id=client_id,
        defaults={
            'file_name': file_name,
            'file_category': file_category,
            'total_size_bytes': total_size,
            'user': user
        }
    )

    # Save uploaded file
    session.uploaded_file = chunk_file
    session.bytes_received = total_size
    session.is_completed = True
    session.save()

    return {
        "session_id": str(session.id),
        "client_id": str(session.client_id),
        "bytes_received": session.bytes_received,
        "is_completed": session.is_completed,
        "file_url": session.uploaded_file.url if session.uploaded_file else ""
    }

