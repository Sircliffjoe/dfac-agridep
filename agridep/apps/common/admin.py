from django.contrib import admin
from django.utils.html import format_html
from agridep.apps.common.models import SystemParameter, ParameterCategory

@admin.register(SystemParameter)
class SystemParameterAdmin(admin.ModelAdmin):
    list_display = (
        'label',
        'key',
        'category_badge',
        'current_value_display',
        'default_value',
        'data_type',
        'updated_at'
    )
    list_filter = ('category', 'data_type')
    search_fields = ('key', 'label', 'description', 'value')
    readonly_fields = ('key', 'data_type', 'default_value', 'created_at', 'updated_at')
    fieldsets = (
        ('Parameter Identity', {
            'fields': ('label', 'key', 'category', 'description')
        }),
        ('Dynamic Configuration (Editable)', {
            'fields': ('value', 'default_value', 'data_type'),
            'description': 'Edit "Value" to immediately alter live decision rules, algorithms, or thresholds without redeploying.'
        }),
        ('Audit Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def category_badge(self, obj):
        colors = {
            ParameterCategory.FIELDOPS: '#2563eb',
            ParameterCategory.FINANCE: '#059669',
            ParameterCategory.MARKET: '#d97706',
            ParameterCategory.TRAINING: '#7c3aed',
            ParameterCategory.PRODUCTION: '#0891b2',
            ParameterCategory.SYSTEM: '#4b5563',
        }
        color = colors.get(obj.category, '#4b5563')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_category_display()
        )
    category_badge.short_description = 'Category'

    def current_value_display(self, obj):
        return format_html(
            '<strong style="color: #111827; font-family: monospace; font-size: 13px;">{}</strong>',
            obj.value
        )
    current_value_display.short_description = 'Live Value'
