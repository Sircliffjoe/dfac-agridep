import math
from decimal import Decimal
from datetime import timedelta
from typing import List, Dict, Any, Optional
from django.db import transaction, models
from django.utils import timezone
from django.core.exceptions import ValidationError

from agridep.apps.market.models import (
    BuyerDemand,
    DemandStatus,
    ProduceMatch,
    MatchStatus,
    OfftakeTransaction,
    OfftakePaymentStatus,
    CommodityPrice,
)
from agridep.apps.production.models import ProduceBatch, ProduceBatchStatus, ProduceQualityGrade
from agridep.apps.audit.services import log_audit_event


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Decimal:
    """Calculates great-circle distance between two GPS coordinates in kilometers."""
    radius_earth_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2.0) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return Decimal(str(round(radius_earth_km * c, 2)))


def find_matching_produce_for_demand(buyer_demand: BuyerDemand) -> List[Dict[str, Any]]:
    """
    Ranks and matches available smallholder produce batches to an off-taker contract.
    Filters on:
    - Enterprise / produce type (e.g. African Catfish)
    - Available status (FORECASTED or AVAILABLE)
    - Harvest delivery window alignment (within +/- 7 day buffer)
    - Spatial radius proximity (farm location within max_delivery_radius_km)
    - Produce quality grade
    """
    buffer_days = timedelta(days=7)
    window_start = buyer_demand.target_delivery_window_start - buffer_days
    window_end = buyer_demand.target_delivery_window_end + buffer_days

    candidate_batches = ProduceBatch.objects.filter(
        produce_type=buyer_demand.enterprise_type,
        status__in=[ProduceBatchStatus.AVAILABLE, ProduceBatchStatus.FORECASTED],
        projected_harvest_window_start__lte=window_end,
        projected_harvest_window_end__gte=window_start
    ).select_related('farm', 'farm__farmer', 'cycle')

    # Filter by minimum quality grade
    grade_hierarchy = {
        ProduceQualityGrade.GRADE_A: 1,
        ProduceQualityGrade.GRADE_B: 2,
        ProduceQualityGrade.GRADE_C: 3
    }
    demand_grade_rank = grade_hierarchy.get(buyer_demand.minimum_grade, 2)

    matches = []
    demand_lat = float(buyer_demand.delivery_latitude)
    demand_lon = float(buyer_demand.delivery_longitude)

    for batch in candidate_batches:
        batch_grade_rank = grade_hierarchy.get(batch.quality_grade, 2)
        if batch_grade_rank > demand_grade_rank:
            continue  # Below buyer minimum grade threshold

        # Distance calculation
        dist_km = Decimal('0.00')
        if batch.farm.latitude is not None and batch.farm.longitude is not None:
            dist_km = haversine_distance_km(
                demand_lat, demand_lon,
                float(batch.farm.latitude), float(batch.farm.longitude)
            )

        if dist_km <= Decimal(str(buyer_demand.max_delivery_radius_km)):
            # Already matched volume on this batch
            existing_allocated = batch.matches.exclude(status=MatchStatus.DECLINED).aggregate(
                total=models.Sum('allocated_volume_kg')
            )['total'] or Decimal('0.00')

            available_vol = max(batch.projected_volume_kg - existing_allocated, Decimal('0.00'))
            if available_vol > Decimal('0.00'):
                matches.append({
                    'batch': batch,
                    'available_volume_kg': available_vol,
                    'distance_km': dist_km,
                    'window_start': batch.projected_harvest_window_start,
                    'window_end': batch.projected_harvest_window_end,
                    'grade': batch.quality_grade,
                    'farm_lga': batch.farm.farmer.lga,
                    'farm_state': batch.farm.farmer.state
                })

    # Sort primarily by distance and secondarily by harvest window alignment
    matches.sort(key=lambda x: (x['distance_km'], x['window_start']))
    return matches


@transaction.atomic
def propose_buyer_matches_for_demand(
    buyer_demand: BuyerDemand,
    auto_allocate: bool = True
) -> List[ProduceMatch]:
    """
    Executes RULE-04 (Buyer-Matching Algorithm):
    Evaluates demand against real-time producer supply pools, aggregates
    smallholders to reach requested tonnage, and generates ProduceMatch records.
    """
    needed_volume = buyer_demand.remaining_unmatched_volume_kg
    if needed_volume <= Decimal('0.00'):
        return []

    candidates = find_matching_produce_for_demand(buyer_demand)
    created_matches = []

    for item in candidates:
        if needed_volume <= Decimal('0.00'):
            break

        batch = item['batch']
        available = item['available_volume_kg']
        allocation = min(available, needed_volume)

        # Create or update ProduceMatch
        match, created = ProduceMatch.objects.get_or_create(
            buyer_demand=buyer_demand,
            produce_batch=batch,
            defaults={
                'allocated_volume_kg': allocation,
                'agreed_price_per_kg_naira': buyer_demand.offered_price_per_kg_naira,
                'distance_km': item['distance_km'],
                'status': MatchStatus.PROPOSED
            }
        )

        if not created:
            match.allocated_volume_kg = allocation
            match.agreed_price_per_kg_naira = buyer_demand.offered_price_per_kg_naira
            match.distance_km = item['distance_km']
            match.save()

        created_matches.append(match)
        needed_volume -= allocation

    # Update buyer demand fulfilled tally
    total_allocated = buyer_demand.matches.exclude(status=MatchStatus.DECLINED).aggregate(
        total=models.Sum('allocated_volume_kg')
    )['total'] or Decimal('0.00')

    buyer_demand.fulfilled_volume_kg = total_allocated
    if buyer_demand.fulfilled_volume_kg >= buyer_demand.target_volume_kg:
        buyer_demand.status = DemandStatus.FULLY_MATCHED
    elif buyer_demand.fulfilled_volume_kg > Decimal('0.00'):
        buyer_demand.status = DemandStatus.PARTIALLY_MATCHED
    buyer_demand.save(update_fields=['fulfilled_volume_kg', 'status', 'updated_at'])

    return created_matches


@transaction.atomic
def confirm_produce_match(match: ProduceMatch, confirmed_by=None) -> OfftakeTransaction:
    """
    Confirms a match into an enforceable commercial off-take contract.
    Generates an official OfftakeTransaction with waybill and unmasks producer PII.
    """
    if match.status == MatchStatus.CONTRACTED and hasattr(match, 'offtake_transaction'):
        return match.offtake_transaction

    match.status = MatchStatus.CONTRACTED
    match.save()

    # Update parent batch status
    batch = match.produce_batch
    batch.status = ProduceBatchStatus.MATCHED
    batch.save(update_fields=['status', 'updated_at'])

    # Create Offtake Transaction
    offtake, created = OfftakeTransaction.objects.get_or_create(
        match=match,
        defaults={
            'actual_delivered_volume_kg': match.allocated_volume_kg,
            'actual_price_per_kg_naira': match.agreed_price_per_kg_naira,
            'total_amount_naira': match.total_value_naira,
            'delivery_date': match.produce_batch.projected_harvest_window_start,
            'payment_status': OfftakePaymentStatus.ESCROW_HELD,
            'quality_inspector': confirmed_by,
            'notes': f"Commercial contract confirmed for {match.allocated_volume_kg:,.0f}kg {match.produce_batch.produce_type.name} with {match.buyer_demand.buyer.company_name}."
        }
    )

    log_audit_event(
        action='CONFIRM_OFFTAKE',
        resource_type='OfftakeTransaction',
        resource_id=str(offtake.id),
        user=confirmed_by,
        details={
            'waybill': offtake.waybill_number,
            'buyer': match.buyer_demand.buyer.company_name,
            'farmer': batch.farm.farmer.full_name,
            'volume_kg': float(match.allocated_volume_kg),
            'total_naira': float(offtake.total_amount_naira)
        }
    )

    return offtake
