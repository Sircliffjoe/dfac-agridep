from django.contrib import admin
from .models import ProductionCycle, ProductionLog, ProduceBatch, HarvestForecast

class ProductionLogInLine(admin.TabularInline):
    model = ProductionLog
    extra = 0
    fields = ('log_date', 'sampling_average_weight_g', 'observed_mortality_count', 'feed_consumed_kg', 'water_temperature_c', 'ph_level')

class ProduceBatchInLine(admin.TabularInline):
    model = ProduceBatch
    extra = 0
    fields = ('produce_type', 'projected_volume_kg', 'projected_harvest_window_start', 'quality_grade', 'status')

@admin.register(ProductionCycle)
class ProductionCycleAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'cycle_name', 'farm', 'enterprise_type', 'current_stock_count', 'current_average_weight_g', 'status', 'projected_harvest_date')
    list_filter = ('status', 'enterprise_type')
    search_fields = ('reference_code', 'cycle_name', 'farm__name')
    readonly_fields = ('reference_code', 'current_stock_count', 'current_average_weight_g', 'created_at', 'updated_at')
    inlines = [ProductionLogInLine, ProduceBatchInLine]

@admin.register(ProductionLog)
class ProductionLogAdmin(admin.ModelAdmin):
    list_display = ('cycle', 'log_date', 'sampling_average_weight_g', 'observed_mortality_count', 'feed_consumed_kg', 'water_temperature_c', 'ph_level')
    list_filter = ('log_date', 'disease_symptoms_observed')
    search_fields = ('cycle__cycle_name', 'cycle__reference_code')

@admin.register(ProduceBatch)
class ProduceBatchAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'farm', 'produce_type', 'projected_volume_kg', 'projected_harvest_window_start', 'quality_grade', 'status')
    list_filter = ('status', 'quality_grade', 'produce_type')
    search_fields = ('reference_code', 'farm__name')
    readonly_fields = ('reference_code', 'created_at', 'updated_at')

@admin.register(HarvestForecast)
class HarvestForecastAdmin(admin.ModelAdmin):
    list_display = ('cycle', 'projected_harvest_date', 'projected_yield_kg', 'confidence_score_pct', 'computed_at')
    readonly_fields = ('computed_at',)
