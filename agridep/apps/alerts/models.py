import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from agridep.apps.common.models import TimeStampedUUIDModel


class AlertChannel(models.TextChoices):
    SMS = 'SMS', 'SMS (Africa\'s Talking)'
    USSD = 'USSD', 'USSD Session Push'
    IN_APP = 'IN_APP', 'Web / Mobile In-App Notification'
    EMAIL = 'EMAIL', 'Email Message'


class AlertPriority(models.TextChoices):
    LOW = 'LOW', 'Low'
    NORMAL = 'NORMAL', 'Normal'
    HIGH = 'HIGH', 'High'
    EMERGENCY = 'EMERGENCY', 'Emergency (Life/Asset Threat)'


class AlertStatus(models.TextChoices):
    QUEUED = 'QUEUED', 'Queued'
    SENT = 'SENT', 'Sent to Gateway'
    DELIVERED = 'DELIVERED', 'Delivered to Handset'
    FAILED = 'FAILED', 'Failed / Gateway Error'


class AlertRule(TimeStampedUUIDModel):
    """Configurable automated notification rule triggered by platform events."""
    rule_code = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default='')
    channel = models.CharField(max_length=16, choices=AlertChannel.choices, default=AlertChannel.SMS)
    priority = models.CharField(max_length=16, choices=AlertPriority.choices, default=AlertPriority.NORMAL)
    message_template = models.TextField(
        help_text="SMS template with merge tags like {farmer_name}, {farm_name}, {amount}, {days}"
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.rule_code}] {self.name} ({self.channel})"


class AlertNotification(TimeStampedUUIDModel):
    """Immutable audit log of all outbound SMS alerts, OTPs, and notifications."""
    rule = models.ForeignKey(AlertRule, null=True, blank=True, on_delete=models.SET_NULL, related_name='notifications')
    recipient_phone = models.CharField(max_length=32, db_index=True)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='notifications'
    )
    channel = models.CharField(max_length=16, choices=AlertChannel.choices, default=AlertChannel.SMS)
    priority = models.CharField(max_length=16, choices=AlertPriority.choices, default=AlertPriority.NORMAL)
    message_text = models.TextField()
    status = models.CharField(max_length=16, choices=AlertStatus.choices, default=AlertStatus.QUEUED, db_index=True)
    provider_reference = models.CharField(max_length=128, blank=True, default='')
    provider_response = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.recipient_phone} [{self.get_channel_display()}] - {self.get_status_display()}"


class USSDSession(TimeStampedUUIDModel):
    """
    State machine store for multi-turn rural USSD sessions.
    Maintains session state across 2G feature phone telecom prompts (*384*223#).
    """
    session_id = models.CharField(max_length=128, unique=True, db_index=True)
    phone_number = models.CharField(max_length=32, db_index=True)
    service_code = models.CharField(max_length=32, default="*384*223#")
    network_code = models.CharField(max_length=32, default="MTN_NG")
    current_menu = models.CharField(max_length=64, default="MAIN_MENU")
    session_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Ephemeral state data (selected farm, input mortality count, pending confirmation)"
    )
    is_active = models.BooleanField(default=True)
    last_interaction_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_interaction_at']

    def __str__(self):
        return f"USSD {self.session_id} [{self.phone_number}] -> {self.current_menu}"
