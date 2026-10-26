import uuid
import json
from decimal import Decimal, InvalidOperation
from django.db import models
from django.conf import settings
from django.core.cache import cache

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


class ParameterCategory(models.TextChoices):
    FIELDOPS = 'FIELDOPS', 'Field Operations & Priority Queue'
    FINANCE = 'FINANCE', 'Finance & Credit Risk'
    MARKET = 'MARKET', 'Market Linkage & Matching'
    TRAINING = 'TRAINING', 'Training & Capacity Building'
    PRODUCTION = 'PRODUCTION', 'Production & Yield Monitoring'
    SYSTEM = 'SYSTEM', 'General Platform Settings'


class ParameterDataType(models.TextChoices):
    DECIMAL = 'DECIMAL', 'Decimal Number'
    INTEGER = 'INTEGER', 'Integer Number'
    STRING = 'STRING', 'Text String'
    BOOLEAN = 'BOOLEAN', 'Boolean (True/False)'
    JSON = 'JSON', 'Structured JSON'


class SystemParameter(TimeStampedUUIDModel):
    """
    Configurable dynamic parameter stored in the database and manageable via Django Admin.
    Eliminates hardcoded values across decision workflows, algorithms, and thresholds.
    """
    key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Unique programmatic lookup key (e.g. fieldops_priority_w1_overdue_weight)"
    )
    category = models.CharField(
        max_length=32,
        choices=ParameterCategory.choices,
        default=ParameterCategory.SYSTEM,
        db_index=True,
        help_text="Operational functional area this parameter belongs to"
    )
    data_type = models.CharField(
        max_length=16,
        choices=ParameterDataType.choices,
        default=ParameterDataType.STRING,
        help_text="Data type for casting and input validation"
    )
    label = models.CharField(
        max_length=255,
        help_text="Human-readable title displayed in the Admin Dashboard"
    )
    description = models.TextField(
        blank=True,
        help_text="Detailed explanation of how this parameter influences decision rules or platform calculations"
    )
    value = models.TextField(
        help_text="Current active setting value (can be edited by administrators)"
    )
    default_value = models.TextField(
        help_text="Original factory default value for safe resetting"
    )

    class Meta:
        ordering = ['category', 'key']
        verbose_name = 'System Parameter'
        verbose_name_plural = 'System Parameters (Dynamic Configuration)'

    def __str__(self):
        return f"{self.label} [{self.key}] = {self.value}"

    def get_typed_value(self):
        """Returns the parameter value cast to its Python data type."""
        raw = self.value.strip() if isinstance(self.value, str) else str(self.value)
        if self.data_type == ParameterDataType.DECIMAL:
            try:
                return Decimal(raw)
            except (InvalidOperation, ValueError):
                return Decimal(self.default_value)
        elif self.data_type == ParameterDataType.INTEGER:
            try:
                return int(float(raw))
            except ValueError:
                return int(float(self.default_value))
        elif self.data_type == ParameterDataType.BOOLEAN:
            return raw.lower() in ('true', '1', 'yes', 't', 'on')
        elif self.data_type == ParameterDataType.JSON:
            try:
                return json.loads(raw)
            except Exception:
                return json.loads(self.default_value)
        return raw

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate cache on change
        cache_key = f"system_param:{self.key}"
        cache.delete(cache_key)

    @classmethod
    def get(cls, key: str, default=None, category=ParameterCategory.SYSTEM, label=None, description=None):
        """
        Retrieves the typed value of a system parameter.
        Uses in-memory/Redis cache for performance.
        If the parameter does not exist in DB, creates it with `default` so that
        it immediately appears in the Django Admin for operators to inspect and modify.
        """
        cache_key = f"system_param:{key}"
        cached_val = cache.get(cache_key)
        if cached_val is not None:
            return cached_val

        try:
            param = cls.objects.filter(key=key).first()
            if param is not None:
                typed = param.get_typed_value()
                cache.set(cache_key, typed, timeout=300)
                return typed

            # Auto-seed if missing and default provided
            if default is not None:
                # Infer type
                if isinstance(default, bool):
                    d_type = ParameterDataType.BOOLEAN
                elif isinstance(default, int):
                    d_type = ParameterDataType.INTEGER
                elif isinstance(default, (float, Decimal)):
                    d_type = ParameterDataType.DECIMAL
                elif isinstance(default, (dict, list)):
                    d_type = ParameterDataType.JSON
                else:
                    d_type = ParameterDataType.STRING

                val_str = json.dumps(default) if d_type == ParameterDataType.JSON else str(default)
                param = cls.objects.create(
                    key=key,
                    category=category,
                    data_type=d_type,
                    label=label or key.replace('_', ' ').title(),
                    description=description or f"Dynamic variable for {key}",
                    value=val_str,
                    default_value=val_str
                )
                typed = param.get_typed_value()
                cache.set(cache_key, typed, timeout=300)
                return typed

        except Exception:
            # Fallback gracefully if database or table is unavailable during migrations
            return default

        return default
