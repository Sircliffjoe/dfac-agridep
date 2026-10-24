import uuid
from django.db import models
from django.conf import settings

class ActiveManager(models.Manager):
    """Manager returning only active (non-deleted) records."""
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

class TimeStampedUUIDModel(models.Model):
    """
    Abstract base model providing:
    - UUIDv4 primary key
    - Human-readable unique reference code (e.g. DFAC-FRM-000123)
    - Timestamp audit fields (created_at, updated_at)
    - Actor audit fields (created_by)
    - Soft-delete flag (is_deleted)
    - Offline-sync idempotency keys (client_id, client_updated_at)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference_code = models.CharField(max_length=64, unique=True, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )
    is_deleted = models.BooleanField(default=False, db_index=True)
    
    # Offline sync support
    client_id = models.UUIDField(null=True, blank=True, db_index=True, help_text="Client-side UUID for offline creation")
    client_updated_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp of edit on client device")

    objects = ActiveManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True
        ordering = ['-created_at']

    def delete(self, using=None, keep_parents=False):
        """Soft delete record by default."""
        self.is_deleted = True
        self.save(update_fields=['is_deleted', 'updated_at'])

    def hard_delete(self):
        """Perform actual database deletion if strictly required."""
        super().delete()
