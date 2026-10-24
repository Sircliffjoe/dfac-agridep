import random
import uuid
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from agridep.apps.common.models import TimeStampedUUIDModel

class UserRole(models.TextChoices):
    DFAC_ADMIN = 'DFAC_ADMIN', 'DFAC Management / Administrator'
    FIELD_OFFICER = 'FIELD_OFFICER', 'Field / Extension Officer'
    TRAINER = 'TRAINER', 'Trainer / Extension Specialist'
    LENDER = 'LENDER', 'Finance / Lender Partner'
    BUYER = 'BUYER', 'Buyer / Off-taker'
    FARMER = 'FARMER', 'Farmer / Smallholder'

class User(AbstractUser):
    """Custom user model for all AgriDEP actors."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(
        max_length=32,
        choices=UserRole.choices,
        default=UserRole.FIELD_OFFICER,
        db_index=True
    )
    phone_number = models.CharField(max_length=32, unique=True, null=True, blank=True, db_index=True)
    is_phone_verified = models.BooleanField(default=False)
    state = models.CharField(max_length=64, blank=True, default="Delta")
    lga = models.CharField(max_length=64, blank=True, default="")

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

class ConsentChannel(models.TextChoices):
    MOBILE_APP = 'MOBILE_APP', 'Flutter Mobile App'
    KOBO_FORM = 'KOBO_FORM', 'KoboToolbox / ODK Form'
    USSD = 'USSD', 'USSD Session'
    SMS = 'SMS', 'SMS Confirmation'
    WRITTEN_FORM = 'WRITTEN_FORM', 'Signed Physical Form'
    WEB_PORTAL = 'WEB_PORTAL', 'Web Portal'

class StakeholderCategory(models.TextChoices):
    FINANCE_LENDER = 'FINANCE_LENDER', 'Credit and Financing Partners'
    OFFTAKE_BUYER = 'OFFTAKE_BUYER', 'Commercial Buyers and Off-takers'
    DONOR_PARTNER = 'DONOR_PARTNER', 'Development Partners (PIND, GIZ)'
    INPUT_SUPPLIER = 'INPUT_SUPPLIER', 'Agricultural Input Suppliers'
    ALL_ECOSYSTEM = 'ALL_ECOSYSTEM', 'Entire AgriDEP Ecosystem'

class ConsentRecord(TimeStampedUUIDModel):
    """
    NDPA 2023 compliant consent record.
    Captures verifiable permission from smallholders regarding how their
    personal, location, and financial data is shared with other ecosystem actors.
    """
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name='consents')
    farmer_reference = models.CharField(max_length=64, db_index=True, help_text="Reference code or ID of the farmer")
    stakeholder_category = models.CharField(max_length=32, choices=StakeholderCategory.choices)
    consent_given = models.BooleanField(default=True)
    consent_scope = models.TextField(help_text="Detailed description of consent granted")
    channel = models.CharField(max_length=32, choices=ConsentChannel.choices, default=ConsentChannel.MOBILE_APP)
    captured_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')

    class Meta:
        verbose_name = "Consent Record (NDPA)"
        verbose_name_plural = "Consent Records (NDPA)"

    def __str__(self):
        return f"Consent for {self.farmer_reference} -> {self.stakeholder_category}: {self.consent_given}"

class OTPToken(models.Model):
    """One-Time Password token for phone verification and SMS login."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=32, db_index=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)

    @classmethod
    def generate_otp(cls, phone_number: str) -> 'OTPToken':
        code = f"{random.randint(100000, 999999)}"
        expires_at = timezone.now() + timedelta(minutes=10)
        return cls.objects.create(
            phone_number=phone_number,
            code=code,
            expires_at=expires_at
        )

    def is_valid(self, input_code: str) -> bool:
        if self.is_used:
            return False
        if timezone.now() > self.expires_at:
            return False
        if self.attempts >= 3:
            return False
        self.attempts += 1
        self.save(update_fields=['attempts'])
        if self.code == input_code:
            self.is_used = True
            self.save(update_fields=['is_used'])
            return True
        return False
