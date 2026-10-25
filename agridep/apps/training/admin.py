from django.contrib import admin
from django.utils.html import format_html
from agridep.apps.training.models import (
    TrainingProgramme,
    TrainingSession,
    Attendance,
    Assessment,
    Certificate,
)
from agridep.apps.training.services import issue_certificate


@admin.register(TrainingProgramme)
class TrainingProgrammeAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'title', 'enterprise_type', 'duration_days', 'min_attendance_pct', 'min_pass_score', 'is_active')
    list_filter = ('enterprise_type', 'is_active')
    search_fields = ('title', 'reference_code', 'description')
    ordering = ('title',)


@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'programme', 'venue', 'lga', 'state', 'start_date', 'end_date', 'status', 'trainer')
    list_filter = ('status', 'state', 'lga', 'programme')
    search_fields = ('reference_code', 'venue', 'programme__title', 'lga')
    ordering = ('-start_date',)
    autocomplete_fields = ('trainer', 'cohort')


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('session', 'farmer', 'date', 'status_badge', 'notes')
    list_filter = ('status', 'date', 'session__programme')
    search_fields = ('farmer__first_name', 'farmer__last_name', 'farmer__reference_code', 'session__reference_code')
    autocomplete_fields = ('farmer', 'session')

    def status_badge(self, obj):
        colors = {
            'PRESENT': '#16A34A',
            'ABSENT': '#DC2626',
            'EXCUSED': '#D97706'
        }
        color = colors.get(obj.status, '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Attendance Status"


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ('session', 'farmer', 'score_display', 'passed_badge', 'assessment_date', 'assessor')
    list_filter = ('passed', 'assessment_date', 'session__programme')
    search_fields = ('farmer__first_name', 'farmer__last_name', 'farmer__reference_code', 'session__reference_code')
    autocomplete_fields = ('farmer', 'session')

    def score_display(self, obj):
        return f"{obj.score}/{obj.max_score}"
    score_display.short_description = "Score"

    def passed_badge(self, obj):
        color = '#16A34A' if obj.passed else '#DC2626'
        label = "PASSED" if obj.passed else "FAILED"
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            label
        )
    passed_badge.short_description = "Result"


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('certificate_number', 'farmer', 'programme', 'issue_date', 'expiry_date', 'status_badge', 'actions_column')
    list_filter = ('is_valid', 'programme', 'issue_date')
    search_fields = ('certificate_number', 'verification_code', 'farmer__first_name', 'farmer__last_name', 'farmer__reference_code')
    readonly_fields = ('certificate_number', 'verification_code', 'pdf_preview', 'qr_preview')
    autocomplete_fields = ('farmer', 'programme', 'session')
    actions = ['issue_missing_pdfs']

    def status_badge(self, obj):
        color = '#16A34A' if obj.is_valid else '#DC2626'
        label = "VALID" if obj.is_valid else "REVOKED"
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            label
        )
    status_badge.short_description = "Status"

    def actions_column(self, obj):
        links = []
        if obj.pdf_file:
            links.append(f'<a href="{obj.pdf_file.url}" target="_blank" style="color: #0F5132; font-weight: bold;">📄 View PDF</a>')
        return format_html(" | ".join(links) if links else "Pending")
    actions_column.short_description = "Document"

    def pdf_preview(self, obj):
        if obj.pdf_file:
            return format_html('<a href="{}" target="_blank">Download Certificate PDF</a>', obj.pdf_file.url)
        return "Not generated yet"

    def qr_preview(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="120" height="120" />', obj.qr_code_image.url)
        return "No QR code"
