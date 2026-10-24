from datetime import date, timedelta
from decimal import Decimal
from django.utils import timezone
from .models import ProductionCycle, ProductionLog, ProduceBatch, HarvestForecast, CycleStage, ProduceBatchStatus

def process_production_log(log: ProductionLog) -> HarvestForecast:
    """
    Core production decision workflow:
    1. Adjusts cycle stock count from observed mortality.
    2. Updates current sampled weight.
    3. Recomputes dynamic harvest yield projection.
    4. Evaluates RULE-01: flags harvest-ready status when within 14 days.
    """
    cycle = log.cycle
    
    # 1. Update stock count
    if log.observed_mortality_count > 0:
        cycle.current_stock_count = max(0, cycle.current_stock_count - log.observed_mortality_count)
    
    # 2. Update weight
    cycle.current_average_weight_g = log.sampling_average_weight_g
    
    # Target harvest weight (default 1.0 kg for table size catfish)
    target_weight_kg = Decimal('1.00')
    current_weight_kg = log.sampling_average_weight_g / Decimal('1000.0')

    # 3. Dynamic yield calculation
    projected_yield_kg = Decimal(cycle.current_stock_count) * target_weight_kg
    
    # Estimate days remaining to target weight
    # Standard catfish growth rate: ~6-8g per day in optimal feeding
    growth_rate_g_per_day = Decimal('7.0')
    weight_deficit_g = max(Decimal('0'), (target_weight_kg * 1000) - log.sampling_average_weight_g)
    days_to_harvest = int(weight_deficit_g / growth_rate_g_per_day) if growth_rate_g_per_day > 0 else 30
    
    today = date.today()
    calculated_harvest_date = today + timedelta(days=days_to_harvest)
    cycle.projected_harvest_date = calculated_harvest_date

    # 4. RULE-01: Harvest-ready evaluation (Within 14 days)
    is_harvest_ready = (calculated_harvest_date - today).days <= 14
    if is_harvest_ready and cycle.status != CycleStage.HARVESTED:
        cycle.status = CycleStage.HARVEST_READY
    elif cycle.status != CycleStage.HARVESTED:
        cycle.status = CycleStage.GROWING
    
    cycle.save(update_fields=['current_stock_count', 'current_average_weight_g', 'projected_harvest_date', 'status'])

    # Update or create Forecast
    forecast, _ = HarvestForecast.objects.update_or_create(
        cycle=cycle,
        defaults={
            'projected_harvest_date': calculated_harvest_date,
            'projected_yield_kg': projected_yield_kg,
            'confidence_score_pct': Decimal('92.00')
        }
    )

    # Sync ProduceBatch
    window_start = calculated_harvest_date - timedelta(days=3)
    window_end = calculated_harvest_date + timedelta(days=7)
    batch_status = ProduceBatchStatus.AVAILABLE if is_harvest_ready else ProduceBatchStatus.FORECASTED

    ProduceBatch.objects.update_or_create(
        cycle=cycle,
        defaults={
            'farm': cycle.farm,
            'produce_type': cycle.enterprise_type,
            'projected_volume_kg': projected_yield_kg,
            'projected_harvest_window_start': window_start,
            'projected_harvest_window_end': window_end,
            'status': batch_status,
        }
    )

    return forecast
