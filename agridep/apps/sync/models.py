import uuid
from django.db import models
from django.conf import settings

class IngestionSource(models.TextChoices):
    KOBO_TOOLBOX = 'KOBO_TOOLBOX', 'KoboToolbox Webhook'
    ODK_COLLECT = 'ODK_COLLECT', 'ODK Aggregate / Central REST'
    FLUTTER_OFFLINE = 'FLUTTER_OFFLINE', 'Flutter Drift SQLite Sync'
    CSV_IMPORT = 'CSV_IMPORT', 'CSV/Excel Bulk Upload'

class IngestionLog(models.Model):
    """Raw ingestion payload store for auditability and idempotency."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=32, choices=IngestionSource.choices)
    submission_id = models.CharField(max_length=128, db_index=True, unique=True, null=True, blank=True)
    raw_payload = models.JSONField()
    processed_status = models.CharField(
        max_length=32,
        choices=[('SUCCESS', 'Success'), ('PARTIAL', 'Partial'), ('FAILED', 'Failed')],
        default='SUCCESS'
    )
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.source} [{self.submission_id}] - {self.processed_status}"

class ConflictLog(models.Model):
    """Logs data sync conflicts between offline client edits and server state."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id = models.UUIDField(db_index=True)
    table_name = models.CharField(max_length=64)
    client_payload = models.JSONField()
    server_payload = models.JSONField()
    resolution_strategy = models.CharField(max_length=32, default="LAST_WRITE_WINS")
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
