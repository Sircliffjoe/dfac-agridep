import pytest
from datetime import date, timedelta
from decimal import Decimal
from agridep.apps.registry.models import Farmer, Farm
from agridep.apps.production.models import ProductionCycle, ProductionLog, CycleStage, ProduceBatchStatus
from agridep.apps.production.services import process_production_log

@pytest.mark.django_db
def test_production_log_biometrics_and_harvest_rule(catfish_enterprise):
    farmer = Farmer.objects.create(
        first_name="Precious",
        last_name="Ojo",
        phone_normalized="+2348031234567",
        state="Delta",
        lga="Warri South"
    )
    farm = Farm.objects.create(
        farmer=farmer,
        name="Ojo Ponds",
        latitude=Decimal('5.544000'),
        longitude=Decimal('5.760000')
    )

    cycle = ProductionCycle.objects.create(
        farm=farm,
        enterprise_type=catfish_enterprise,
        cycle_name="Pond 1 Stock 2026",
        start_date=date.today() - timedelta(days=120),
        projected_harvest_date=date.today() + timedelta(days=30),
        initial_stock_count=5000,
        current_stock_count=5000,
        initial_average_weight_g=Decimal('15.0'),
        current_average_weight_g=Decimal('500.0'),
        status=CycleStage.GROWING
    )

    # 1. Log observation with 20 mortality and 950g sample weight (very close to table size 1000g)
    log = ProductionLog.objects.create(
        cycle=cycle,
        sampling_average_weight_g=Decimal('950.0'),
        observed_mortality_count=20,
        feed_consumed_kg=Decimal('60.0'),
        water_temperature_c=Decimal('28.0'),
        ph_level=Decimal('7.2')
    )

    forecast = process_production_log(log)
    cycle.refresh_from_db()

    # Assert stock count adjusted for mortality
    assert cycle.current_stock_count == 4980
    assert cycle.current_average_weight_g == Decimal('950.0')

    # At 950g with 7g/day growth, weight deficit is 50g -> ~7 days to 1kg target!
    # RULE-01: <= 14 days triggers HARVEST_READY!
    assert cycle.status == CycleStage.HARVEST_READY
    assert forecast.projected_yield_kg == Decimal('4980') * Decimal('1.00')

    # Produce batch is open for off-take
    batch = cycle.produce_batches.first()
    assert batch is not None
    assert batch.status == ProduceBatchStatus.AVAILABLE
