from django.contrib import admin
from .models import AuditEvent

@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ('action', 'resource_type', 'resource_id', 'user', 'ip_address', 'timestamp')
    list_filter = ('action', 'resource_type')
    search_fields = ('resource_id', 'user__username', 'ip_address')
    readonly_fields = ('id', 'user', 'action', 'resource_type', 'resource_id', 'ip_address', 'user_agent', 'details', 'timestamp')
