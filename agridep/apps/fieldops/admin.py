from decimal import Decimal
from django.contrib import admin, messages
from django.utils.html import format_html
from agridep.apps.fieldops.models import (
    FarmVisit,
    FarmVisitStatus,
    Inspection,
    InspectionPhoto,
    IncidentReport,
    IncidentSeverity,
    VisitAssignment,
    AssignmentPriority,
)
from agridep.apps.fieldops.services import (
    auto_generate_visit_assignments,
    verify_geofence,
)


class InspectionPhotoInline(admin.TabularInline):
    model = InspectionPhoto
    extra = 0
    fields = ('photo', 'category', 'caption', 'latitude', 'longitude', 'is_geofence_verified', 'distance_to_farm_meters')
    readonly_fields = ('is_geofence_verified', 'distance_to_farm_meters')


class InspectionInline(admin.StackedInline):
    model = Inspection
    extra = 0
    fields = (
        'inspection_type',
        'compliance_rating',
        ('water_ph', 'water_temperature_celsius', 'dissolved_oxygen_mg_l', 'ammonia_ppm'),
        ('average_sample_weight_grams', 'daily_mortality_count', 'feed_inventory_kg'),
        'biosecurity_protocol_followed',
        'corrective_actions',
        'summary_findings',
    )


@admin.register(FarmVisit)
class FarmVisitAdmin(admin.ModelAdmin):
    list_display = (
        'reference_code',
        'farm_name',
        'farmer_name',
        'officer',
        'scheduled_date',
        'status_badge',
        'purpose',
        'geofence_status_badge',
        'distance_display',
    )
    list_filter = ('status', 'purpose', 'is_geofence_verified', 'scheduled_date')
    search_fields = ('reference_code', 'farm__name', 'farm__farmer__first_name', 'farm__farmer__last_name', 'officer__username')
    readonly_fields = ('reference_code', 'is_geofence_verified', 'distance_to_farm_meters', 'created_at', 'updated_at')
    inlines = [InspectionInline]
    actions = ['verify_selected_geofences']

    def farm_name(self, obj):
        return obj.farm.name
    farm_name.short_description = "Farm"

    def farmer_name(self, obj):
        return obj.farm.farmer.full_name
    farmer_name.short_description = "Farmer"

    def status_badge(self, obj):
        colors = {
            FarmVisitStatus.COMPLETED: '#059669',
            FarmVisitStatus.IN_PROGRESS: '#2563eb',
            FarmVisitStatus.SCHEDULED: '#d97706',
            FarmVisitStatus.CANCELLED: '#6b7280',
            FarmVisitStatus.MISSED: '#dc2626',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def geofence_status_badge(self, obj):
        if obj.is_geofence_verified:
            return format_html(
                '<span style="background-color: #059669; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">✓ Verified On-Site</span>'
            )
        elif obj.latitude is not None:
            return format_html(
                '<span style="background-color: #dc2626; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">⚠ Geofence Drift</span>'
            )
        return format_html('<span style="color: #6b7280; font-size: 11px;">No GPS</span>')
    geofence_status_badge.short_description = "Geofence"

    def distance_display(self, obj):
        if obj.distance_to_farm_meters is not None:
            return f"{obj.distance_to_farm_meters:.1f} m"
        return "-"
    distance_display.short_description = "Drift Distance"

    @admin.action(description="Verify GPS geofence against registered farm coordinates")
    def verify_selected_geofences(self, request, queryset):
        count = 0
        for visit in queryset:
            if visit.latitude is not None and visit.longitude is not None:
                is_verified, distance = verify_geofence(visit.farm, visit.latitude, visit.longitude)
                visit.is_geofence_verified = is_verified
                visit.distance_to_farm_meters = distance
                visit.save(update_fields=['is_geofence_verified', 'distance_to_farm_meters'])
                count += 1
        messages.success(request, f"Re-verified geofence calculation for {count} visits.")


@admin.register(Inspection)
class InspectionAdmin(admin.ModelAdmin):
    list_display = (
        'reference_code',
        'visit_code',
        'farm_name',
        'inspection_type',
        'compliance_badge',
        'water_quality_summary',
        'created_at',
    )
    list_filter = ('inspection_type', 'compliance_rating', 'biosecurity_protocol_followed')
    search_fields = ('reference_code', 'visit__reference_code', 'visit__farm__name')
    readonly_fields = ('reference_code', 'created_at', 'updated_at')
    inlines = [InspectionPhotoInline]

    def visit_code(self, obj):
        return obj.visit.reference_code
    visit_code.short_description = "Visit Ref"

    def farm_name(self, obj):
        return obj.visit.farm.name
    farm_name.short_description = "Farm"

    def compliance_badge(self, obj):
        color = '#059669' if 'EXCELLENT' in obj.compliance_rating or 'SATISFACTORY' in obj.compliance_rating else '#dc2626'
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_compliance_rating_display()
        )
    compliance_badge.short_description = "Compliance"

    def water_quality_summary(self, obj):
        parts = []
        if obj.water_ph:
            parts.append(f"pH: {obj.water_ph}")
        if obj.dissolved_oxygen_mg_l:
            parts.append(f"DO: {obj.dissolved_oxygen_mg_l} mg/L")
        if obj.water_temperature_celsius:
            parts.append(f"{obj.water_temperature_celsius}°C")
        return " | ".join(parts) if parts else "-"
    water_quality_summary.short_description = "Water Biometrics"


@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = (
        'reference_code',
        'title',
        'farm_name',
        'severity_badge',
        'incident_type',
        'status',
        'reported_at',
    )
    list_filter = ('severity', 'status', 'incident_type', 'reported_at')
    search_fields = ('reference_code', 'title', 'farm__name', 'description')
    readonly_fields = ('reference_code', 'reported_at', 'created_at', 'updated_at')

    def farm_name(self, obj):
        return obj.farm.name
    farm_name.short_description = "Farm"

    def severity_badge(self, obj):
        colors = {
            IncidentSeverity.CRITICAL: '#b91c1c',
            IncidentSeverity.HIGH: '#ea580c',
            IncidentSeverity.MEDIUM: '#d97706',
            IncidentSeverity.LOW: '#0284c7',
        }
        color = colors.get(obj.severity, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_severity_display()
        )
    severity_badge.short_description = "Severity"


@admin.register(VisitAssignment)
class VisitAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        'reference_code',
        'farm_name',
        'assigned_officer',
        'priority_score',
        'priority_badge',
        'trigger_reason',
        'status',
        'due_date',
        'auto_generated',
    )
    list_filter = ('priority_level', 'status', 'trigger_reason', 'auto_generated')
    search_fields = ('reference_code', 'farm__name', 'assigned_officer__username')
    readonly_fields = ('reference_code', 'priority_score', 'scoring_breakdown', 'created_at', 'updated_at')
    actions = ['trigger_auto_dispatch']

    def farm_name(self, obj):
        return obj.farm.name
    farm_name.short_description = "Farm"

    def priority_badge(self, obj):
        colors = {
            AssignmentPriority.URGENT: '#b91c1c',
            AssignmentPriority.HIGH: '#ea580c',
            AssignmentPriority.MEDIUM: '#d97706',
            AssignmentPriority.LOW: '#059669',
        }
        color = colors.get(obj.priority_level, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_priority_level_display()
        )
    priority_badge.short_description = "Priority"

    @admin.action(description="Run Decision Engine Priority Scanner & Auto-Dispatch Assignments")
    def trigger_auto_dispatch(self, request, queryset):
        created = auto_generate_visit_assignments()
        messages.success(request, f"Decision Engine created {len(created)} urgent visit assignments.")
