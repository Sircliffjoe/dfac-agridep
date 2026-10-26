from django.contrib import admin
from django.utils.html import format_html
from agridep.apps.alerts.models import AlertNotification, AlertRule, USSDSession, AlertStatus, AlertPriority


@admin.register(AlertNotification)
class AlertNotificationAdmin(admin.ModelAdmin):
    list_display = (
        'recipient_phone',
        'channel',
        'priority_badge',
        'status_badge',
        'short_message',
        'provider_reference',
        'created_at',
    )
    list_filter = ('channel', 'status', 'priority', 'created_at')
    search_fields = ('recipient_phone', 'message_text', 'provider_reference')
    readonly_fields = ('created_at', 'sent_at', 'delivered_at', 'provider_response')

    def short_message(self, obj):
        return obj.message_text[:60] + ('...' if len(obj.message_text) > 60 else '')
    short_message.short_description = "Message"

    def status_badge(self, obj):
        colors = {
            AlertStatus.DELIVERED: '#059669',
            AlertStatus.SENT: '#2563eb',
            AlertStatus.QUEUED: '#d97706',
            AlertStatus.FAILED: '#dc2626',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Status"

    def priority_badge(self, obj):
        colors = {
            AlertPriority.EMERGENCY: '#dc2626',
            AlertPriority.HIGH: '#ea580c',
            AlertPriority.NORMAL: '#0284c7',
            AlertPriority.LOW: '#6b7280',
        }
        color = colors.get(obj.priority, '#6b7280')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: bold;">{}</span>',
            color,
            obj.get_priority_display()
        )
    priority_badge.short_description = "Priority"


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ('rule_code', 'name', 'channel', 'priority', 'is_active')
    list_filter = ('channel', 'priority', 'is_active')
    search_fields = ('rule_code', 'name', 'message_template')


@admin.register(USSDSession)
class USSDSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'phone_number', 'current_menu', 'is_active', 'last_interaction_at')
    list_filter = ('is_active', 'network_code', 'current_menu')
    search_fields = ('session_id', 'phone_number')
    readonly_fields = ('session_id', 'phone_number', 'service_code', 'created_at', 'updated_at', 'last_interaction_at')
