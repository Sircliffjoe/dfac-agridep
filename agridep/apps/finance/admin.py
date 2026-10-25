from django.contrib import admin
from django.utils.html import format_html
from agridep.apps.finance.models import (
    Lender,
    LoanRecord,
    LoanTranche,
    RepaymentSchedule,
    Repayment,
    RiskFlag,
)


@admin.register(Lender)
class LenderAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'institution_name', 'institution_type', 'contact_person', 'phone', 'concessionary_rate_pct', 'is_active')
    list_filter = ('institution_type', 'is_active')
    search_fields = ('institution_name', 'contact_person', 'reference_code')


class LoanTrancheInline(admin.TabularInline):
    model = LoanTranche
    extra = 0
    fields = ('tranche_number', 'amount_naira', 'tranche_type', 'status', 'milestone_conditions')


class RepaymentScheduleInline(admin.TabularInline):
    model = RepaymentSchedule
    extra = 0
    fields = ('installment_number', 'due_date', 'expected_amount_naira', 'paid_amount_naira', 'status')


@admin.register(LoanRecord)
class LoanRecordAdmin(admin.ModelAdmin):
    list_display = (
        'reference_code',
        'farmer',
        'lender',
        'principal_amount_display',
        'outstanding_display',
        'status_badge',
        'credit_score',
        'application_date'
    )
    list_filter = ('status', 'lender', 'application_date')
    search_fields = ('reference_code', 'farmer__first_name', 'farmer__last_name', 'farmer__reference_code')
    autocomplete_fields = ('farmer', 'lender', 'farm', 'production_cycle')
    inlines = [LoanTrancheInline, RepaymentScheduleInline]

    def principal_amount_display(self, obj):
        return f"₦{obj.principal_amount_naira:,.2f}"
    principal_amount_display.short_description = "Principal"

    def outstanding_display(self, obj):
        return f"₦{obj.outstanding_balance_naira:,.2f}"
    outstanding_display.short_description = "Outstanding Balance"

    def status_badge(self, obj):
        colors = {
            'APPLIED': '#6B7280',
            'APPROVED': '#3B82F6',
            'DISBURSED': '#10B981',
            'PERFORMING': '#16A34A',
            'WATCHLIST': '#F59E0B',
            'DELINQUENT': '#DC2626',
            'REPAID': '#047857',
            'WRITTEN_OFF': '#1F2937',
        }
        color = colors.get(obj.status, '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"


@admin.register(LoanTranche)
class LoanTrancheAdmin(admin.ModelAdmin):
    list_display = ('reference_code', 'loan', 'tranche_number', 'amount_naira', 'tranche_type', 'status', 'disbursement_date')
    list_filter = ('status', 'tranche_type')
    search_fields = ('reference_code', 'loan__reference_code')


@admin.register(Repayment)
class RepaymentAdmin(admin.ModelAdmin):
    list_display = ('transaction_reference', 'loan', 'amount_display', 'payment_date', 'payment_method', 'recorded_by')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('transaction_reference', 'loan__reference_code')

    def amount_display(self, obj):
        return f"₦{obj.amount_naira:,.2f}"
    amount_display.short_description = "Amount Remitted"


@admin.register(RiskFlag)
class RiskFlagAdmin(admin.ModelAdmin):
    list_display = ('rule_triggered', 'farmer', 'loan', 'severity_badge', 'title', 'is_resolved', 'created_at')
    list_filter = ('severity', 'is_resolved', 'rule_triggered')
    search_fields = ('title', 'description', 'farmer__first_name', 'farmer__last_name', 'loan__reference_code')

    def severity_badge(self, obj):
        colors = {
            'LOW': '#3B82F6',
            'MEDIUM': '#F59E0B',
            'HIGH': '#EA580C',
            'CRITICAL': '#DC2626',
        }
        color = colors.get(obj.severity, '#6B7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_severity_display()
        )
    severity_badge.short_description = "Severity"
