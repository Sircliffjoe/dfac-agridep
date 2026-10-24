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
from agridep.apps.accounts.models import ConsentRecord, StakeholderCategory, ConsentChannel
from .models import IngestionLog, IngestionSource, ConflictLog

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

    # Scope to field officer assignment if applicable
    if user and getattr(user, 'role', '') == 'FIELD_OFFICER':
        farmers_qs = farmers_qs.filter(assigned_officer=user)
        farms_qs = farms_qs.filter(farmer__assigned_officer=user)
        cycles_qs = cycles_qs.filter(farm__farmer__assigned_officer=user)
        logs_qs = logs_qs.filter(cycle__farm__farmer__assigned_officer=user)

    if since_dt:
        farmers_qs = farmers_qs.filter(updated_at__gte=since_dt)
        farms_qs = farms_qs.filter(updated_at__gte=since_dt)
        cycles_qs = cycles_qs.filter(updated_at__gte=since_dt)
        logs_qs = logs_qs.filter(updated_at__gte=since_dt)

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
        }
    }
