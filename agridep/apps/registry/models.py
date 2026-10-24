import uuid
from django.db import models
from django.conf import settings
from agridep.apps.common.models import TimeStampedUUIDModel
from agridep.apps.common.encryption import encrypt_value, decrypt_value, hash_deterministic

class EnterpriseCategory(models.TextChoices):
    AQUACULTURE = 'AQUACULTURE', 'Aquaculture (Catfish, Tilapia)'
    LIVESTOCK = 'LIVESTOCK', 'Livestock (Poultry, Snail)'
    CROPS = 'CROPS', 'Arable Crops (Cassava, Maize, Vegetables)'

class EnterpriseType(TimeStampedUUIDModel):
    """Configurable enterprise types seeded as data, not hardcoded."""
    name = models.CharField(max_length=64, unique=True)
    code = models.CharField(max_length=32, unique=True)
    category = models.CharField(max_length=32, choices=EnterpriseCategory.choices)
    standard_cycle_days = models.PositiveIntegerField(default=150, help_text="Typical duration from stocking to harvest in days")
    benchmark_fcr = models.DecimalField(max_digits=4, decimal_places=2, default=1.20, help_text="Feed Conversion Ratio benchmark")
    expected_mortality_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=8.00)
    reference_price_per_kg_naira = models.DecimalField(max_digits=10, decimal_places=2, default=2500.00)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"

class Cohort(TimeStampedUUIDModel):
    """Cohort / Area grouping for field officer assignment and multi-tenant scoping."""
    name = models.CharField(max_length=128)
    state = models.CharField(max_length=64, default="Delta")
    lga = models.CharField(max_length=64)
    lead_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='led_cohorts'
    )

    def __str__(self):
        return f"{self.name} - {self.lga}, {self.state}"

class VerificationStatus(models.TextChoices):
    VERIFIED = 'VERIFIED', 'Verified Smallholder'
    PENDING_REVIEW = 'PENDING_REVIEW', 'Pending Verification'
    FLAGGED_DUPLICATE = 'FLAGGED_DUPLICATE', 'Flagged as Duplicate / Suspicious'

class Farmer(TimeStampedUUIDModel):
    """Anchor identity entity for smallholders."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='farmer_profile'
    )
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64)
    gender = models.CharField(max_length=16, choices=[('MALE', 'Male'), ('FEMALE', 'Female')], default='MALE')
    dob = models.DateField(null=True, blank=True)
    household_size = models.PositiveSmallIntegerField(default=4)
    primary_language = models.CharField(max_length=32, default="English/Pidgin")

    # Encrypted sensitive PII for NDPA 2023 compliance
    phone_encrypted = models.TextField(blank=True, default='')
    phone_normalized = models.CharField(max_length=32, db_index=True, help_text="E.164 phone or masked representation")
    nin_encrypted = models.TextField(blank=True, default='')
    nin_hash = models.CharField(max_length=64, db_index=True, blank=True, default='', help_text="Deterministic SHA-256 hash for deduplication")

    # Geography
    state = models.CharField(max_length=64, default="Delta")
    lga = models.CharField(max_length=64)
    community_address = models.TextField(blank=True, default='')

    # Assignment & scoping
    cohort = models.ForeignKey(Cohort, null=True, blank=True, on_delete=models.SET_NULL, related_name='farmers')
    assigned_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='assigned_farmers'
    )

    verification_status = models.CharField(
        max_length=32,
        choices=VerificationStatus.choices,
        default=VerificationStatus.VERIFIED
    )
    duplicate_review_notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.reference_code or self.id})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            # Generate human-readable code
            count = Farmer.all_objects.count() + 1
            self.reference_code = f"DFAC-FRM-{count:06d}"
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def set_nin(self, raw_nin: str):
        if raw_nin:
            self.nin_encrypted = encrypt_value(raw_nin.strip())
            self.nin_hash = hash_deterministic(raw_nin.strip())
        else:
            self.nin_encrypted = ""
            self.nin_hash = ""

    def get_nin(self) -> str:
        return decrypt_value(self.nin_encrypted)

class Farm(TimeStampedUUIDModel):
    """Anchor identity entity for farming locations, ponds, and plots."""
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='farms')
    name = models.CharField(max_length=128, default="Main Farm Facility")
    
    # Universal coordinates (latitude & longitude)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, help_text="GPS Latitude (WGS84)")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, help_text="GPS Longitude (WGS84)")
    community = models.CharField(max_length=128, blank=True, default='')
    
    # Facilities
    total_area_hectares = models.DecimalField(max_digits=8, decimal_places=2, default=0.50)
    number_of_ponds = models.PositiveSmallIntegerField(default=4, help_text="Total operational ponds")
    total_water_surface_sqm = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    water_source = models.CharField(
        max_length=32,
        choices=[('BOREHOLE', 'Borehole'), ('STREAM_RIVER', 'Stream/River'), ('WELL', 'Well'), ('RAINWATER', 'Rainwater Harvesting')],
        default='BOREHOLE'
    )
    enterprise_types = models.ManyToManyField(EnterpriseType, related_name='farms')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.farmer.full_name} ({self.reference_code or self.id})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = Farm.all_objects.count() + 1
            self.reference_code = f"DFAC-FAR-{count:06d}"
        super().save(*args, **kwargs)

class BuyerTier(models.TextChoices):
    AGGREGATOR = 'AGGREGATOR', 'Regional Aggregator'
    PROCESSOR = 'PROCESSOR', 'Fish/Food Processing Plant'
    EXPORTER = 'EXPORTER', 'Commercial Exporter'
    RETAILER = 'RETAILER', 'Supermarket / Retail Chain'
    HOTEL_RESTAURANT = 'HOTEL_RESTAURANT', 'Hospitality / Restaurant Off-taker'

class Buyer(TimeStampedUUIDModel):
    """Anchor identity entity for off-takers and commercial buyers."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='buyer_profile'
    )
    company_name = models.CharField(max_length=128)
    rc_number = models.CharField(max_length=32, blank=True, default='', help_text="CAC Registration Number")
    contact_name = models.CharField(max_length=64)
    phone = models.CharField(max_length=32)
    email = models.EmailField(blank=True, default='')
    tier = models.CharField(max_length=32, choices=BuyerTier.choices, default=BuyerTier.AGGREGATOR)
    operating_states = models.CharField(max_length=255, default="Delta, Bayelsa, Rivers")
    is_verified = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.company_name} ({self.get_tier_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = Buyer.all_objects.count() + 1
            self.reference_code = f"DFAC-BYR-{count:06d}"
        super().save(*args, **kwargs)
