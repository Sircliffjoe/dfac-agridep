import uuid
from django.db import models
from django.conf import settings

class AuditAction(models.TextChoices):
    READ_SENSITIVE_PII = 'READ_SENSITIVE_PII', 'Sensitive PII Accessed'
    CREATE = 'CREATE', 'Record Created'
    UPDATE = 'UPDATE', 'Record Updated'
    DELETE = 'DELETE', 'Record Soft Deleted'
    FINANCIAL_READ = 'FINANCIAL_READ', 'Financial Ledger Accessed'
    EXPORT_DATA = 'EXPORT_DATA', 'Data Exported'

class AuditEvent(models.Model):
    """
    Immutable audit log for NDPA 2023 compliance and financial accountability.
    Tracks every access to sensitive farmer data and all financial mutations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    action = models.CharField(max_length=32, choices=AuditAction.choices, db_index=True)
    resource_type = models.CharField(max_length=64, db_index=True)
    resource_id = models.CharField(max_length=64, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    details = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['resource_type', 'resource_id']),
            models.Index(fields=['action', 'timestamp']),
        ]

    def __str__(self):
        actor = self.user.username if self.user else "System/Anonymous"
        return f"[{self.timestamp}] {actor} - {self.action} on {self.resource_type}:{self.resource_id}"
