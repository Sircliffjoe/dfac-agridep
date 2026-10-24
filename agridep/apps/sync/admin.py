from django.contrib import admin
from .models import IngestionLog, ConflictLog

@admin.register(IngestionLog)
class IngestionLogAdmin(admin.ModelAdmin):
    list_display = ('source', 'submission_id', 'processed_status', 'created_at')
    list_filter = ('source', 'processed_status')
    search_fields = ('submission_id',)
    readonly_fields = ('created_at',)

@admin.register(ConflictLog)
class ConflictLogAdmin(admin.ModelAdmin):
    list_display = ('client_id', 'table_name', 'resolution_strategy', 'created_at')
    list_filter = ('table_name', 'resolution_strategy')
    search_fields = ('client_id',)
    readonly_fields = ('created_at',)
