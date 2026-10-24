from django.db import models
from django.utils import timezone
from datetime import timedelta
from agridep.apps.common.models import TimeStampedUUIDModel
from agridep.apps.registry.models import Farm, EnterpriseType

class CycleStage(models.TextChoices):
    PREPARATION = 'PREPARATION', 'Site / Pond Preparation'
    STOCKED = 'STOCKED', 'Stocked / Planted'
    GROWING = 'GROWING', 'Active Growth & Feeding'
    HARVEST_READY = 'HARVEST_READY', 'Harvest-Ready (Off-take Window Open)'
    HARVESTED = 'HARVESTED', 'Harvest Completed'
    ABORTED = 'ABORTED', 'Aborted (Disease/Loss)'

class ProductionCycle(TimeStampedUUIDModel):
    """Tracks a single production cycle for aquaculture ponds or crop fields."""
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='production_cycles')
    enterprise_type = models.ForeignKey(EnterpriseType, on_delete=models.PROTECT, related_name='cycles')
    cycle_name = models.CharField(max_length=128, default="Cycle 1 - Pond 1")
    start_date = models.DateField(default=timezone.now)
    projected_harvest_date = models.DateField()
    actual_harvest_date = models.DateField(null=True, blank=True)
    
    # Biometric metrics
    initial_stock_count = models.PositiveIntegerField(help_text="Initial fingerling count or seeds planted")
    current_stock_count = models.PositiveIntegerField(help_text="Estimated live stock count adjusted for mortality")
    initial_average_weight_g = models.DecimalField(max_digits=6, decimal_places=2, default=10.0, help_text="Starting weight in grams")
    current_average_weight_g = models.DecimalField(max_digits=6, decimal_places=2, default=10.0, help_text="Latest sample weight in grams")
    
    status = models.CharField(max_length=32, choices=CycleStage.choices, default=CycleStage.STOCKED, db_index=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.cycle_name} ({self.farm.name}) - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = ProductionCycle.all_objects.count() + 1
            self.reference_code = f"DFAC-CYC-{count:06d}"
        if not self.current_stock_count:
            self.current_stock_count = self.initial_stock_count
        if not self.projected_harvest_date and self.enterprise_type:
            self.projected_harvest_date = self.start_date + timedelta(days=self.enterprise_type.standard_cycle_days)
        super().save(*args, **kwargs)

class ProductionLog(TimeStampedUUIDModel):
    """Periodic biometric and operational observations recorded by farmers or extension agents."""
    cycle = models.ForeignKey(ProductionCycle, on_delete=models.CASCADE, related_name='logs')
    log_date = models.DateField(default=timezone.now)
    sampling_average_weight_g = models.DecimalField(max_digits=6, decimal_places=2, help_text="Average weight sampled (grams)")
    observed_mortality_count = models.PositiveIntegerField(default=0, help_text="Dead fish/livestock removed")
    feed_consumed_kg = models.DecimalField(max_digits=8, decimal_places=2, default=0.0, help_text="Total feed applied since last log")
    feed_brand = models.CharField(max_length=64, blank=True, default="Skretting/Aller Aqua")
    
    # Water Quality Parameters for Aquaculture
    water_temperature_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    ph_level = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    dissolved_oxygen_ppm = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    ammonia_level = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    
    disease_symptoms_observed = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-log_date', '-created_at']

    def __str__(self):
        return f"Log {self.log_date} - {self.cycle.cycle_name} ({self.sampling_average_weight_g}g)"

class ProduceQualityGrade(models.TextChoices):
    GRADE_A = 'GRADE_A', 'Grade A (Table Size 1kg+, Premium Health)'
    GRADE_B = 'GRADE_B', 'Grade B (Standard 600g-900g)'
    GRADE_C = 'GRADE_C', 'Grade C (Under-sized / Mixed)'

class ProduceBatchStatus(models.TextChoices):
    FORECASTED = 'FORECASTED', 'Forecasted Supply'
    AVAILABLE = 'AVAILABLE', 'Harvest-Ready / Open for Off-take'
    MATCHED = 'MATCHED', 'Matched to Buyer Contract'
    DELIVERED = 'DELIVERED', 'Delivered & Closed'

class ProduceBatch(TimeStampedUUIDModel):
    """Identity anchor for marketable produce derived from production cycles."""
    cycle = models.ForeignKey(ProductionCycle, on_delete=models.CASCADE, related_name='produce_batches')
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='produce_batches')
    produce_type = models.ForeignKey(EnterpriseType, on_delete=models.PROTECT)
    projected_volume_kg = models.DecimalField(max_digits=10, decimal_places=2, help_text="Estimated net harvest weight")
    actual_volume_kg = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    projected_harvest_window_start = models.DateField()
    projected_harvest_window_end = models.DateField()
    quality_grade = models.CharField(max_length=16, choices=ProduceQualityGrade.choices, default=ProduceQualityGrade.GRADE_A)
    status = models.CharField(max_length=32, choices=ProduceBatchStatus.choices, default=ProduceBatchStatus.FORECASTED, db_index=True)

    class Meta:
        ordering = ['projected_harvest_window_start']

    def __str__(self):
        return f"{self.produce_type.name} - {self.projected_volume_kg}kg ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = ProduceBatch.all_objects.count() + 1
            self.reference_code = f"DFAC-BTH-{count:06d}"
        super().save(*args, **kwargs)

class HarvestForecast(TimeStampedUUIDModel):
    """Dynamic harvest model prediction updated upon each log entry."""
    cycle = models.OneToOneField(ProductionCycle, on_delete=models.CASCADE, related_name='forecast')
    computed_at = models.DateTimeField(auto_now=True)
    projected_harvest_date = models.DateField()
    projected_yield_kg = models.DecimalField(max_digits=10, decimal_places=2)
    confidence_score_pct = models.DecimalField(max_digits=5, decimal_places=2, default=90.0)

    def __str__(self):
        return f"Forecast for {self.cycle.cycle_name}: {self.projected_yield_kg}kg on {self.projected_harvest_date}"
