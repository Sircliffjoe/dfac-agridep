from django.contrib import admin
from .models import EnterpriseType, Cohort, Farmer, Farm, Buyer

@admin.register(EnterpriseType)
class EnterpriseTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'category', 'standard_cycle_days', 'reference_price_per_kg_naira', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('name', 'code')

@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    list_display = ('name', 'state', 'lga', 'lead_officer', 'created_at')
    list_filter = ('state', 'lga')
    search_fields = ('name', 'lga')

class FarmInline(admin.TabularInline):
    model = Farm
    extra = 0
    fields = ('name', 'latitude', 'longitude', 'number_of_ponds', 'total_area_hectares', 'water_source')

@admin.register(Farmer)
class FarmerAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'first_name', 'last_name', 'phone_normalized', 'state', 'lga', 'verification_status', 'created_at')
    list_filter = ('verification_status', 'state', 'lga', 'gender')
    search_fields = ('reference_code', 'first_name', 'last_name', 'phone_normalized')
    readonly_fields = ('reference_code', 'nin_hash', 'created_at', 'updated_at')
    inlines = [FarmInline]

@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'name', 'farmer', 'latitude', 'longitude', 'number_of_ponds', 'total_area_hectares', 'water_source')
    list_filter = ('water_source',)
    search_fields = ('reference_code', 'name', 'farmer__first_name', 'farmer__last_name')
    readonly_fields = ('reference_code', 'created_at', 'updated_at')

@admin.register(Buyer)
class BuyerAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'company_name', 'tier', 'contact_name', 'phone', 'is_verified')
    list_filter = ('tier', 'is_verified')
    search_fields = ('reference_code', 'company_name', 'contact_name', 'phone')
    readonly_fields = ('reference_code', 'created_at', 'updated_at')
