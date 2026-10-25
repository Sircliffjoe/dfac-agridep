import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from agridep.apps.common.models import TimeStampedUUIDModel
from agridep.apps.registry.models import Buyer, EnterpriseType
from agridep.apps.production.models import ProduceBatch, ProduceQualityGrade


class DemandStatus(models.TextChoices):
    OPEN = 'OPEN', 'Open for Supply Matching'
    PARTIALLY_MATCHED = 'PARTIALLY_MATCHED', 'Partially Matched'
    FULLY_MATCHED = 'FULLY_MATCHED', 'Fully Matched to Batches'
    CONTRACTED = 'CONTRACTED', 'Contracted with Producers'
    FULFILLED = 'FULFILLED', 'Delivery Completed'
    CANCELLED = 'CANCELLED', 'Cancelled by Off-taker'
    EXPIRED = 'EXPIRED', 'Delivery Window Expired'


class BuyerDemand(TimeStampedUUIDModel):
    """Aggregate or specific commercial purchase request logged by verified buyers."""
    buyer = models.ForeignKey(
        Buyer,
        on_delete=models.CASCADE,
        related_name='demands'
    )
    enterprise_type = models.ForeignKey(
        EnterpriseType,
        on_delete=models.CASCADE,
        related_name='demands'
    )
    target_volume_kg = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total requested volume in kilograms")
    fulfilled_volume_kg = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    offered_price_per_kg_naira = models.DecimalField(max_digits=10, decimal_places=2, help_text="Offered contract price in ₦/kg")
    minimum_grade = models.CharField(max_length=16, choices=ProduceQualityGrade.choices, default=ProduceQualityGrade.GRADE_A)
    target_delivery_window_start = models.DateField()
    target_delivery_window_end = models.DateField()
    delivery_state = models.CharField(max_length=64, default="Delta")
    delivery_lga = models.CharField(max_length=64, default="Warri South")
    delivery_address = models.TextField(blank=True, help_text="Processing facility or depot reception address")
    delivery_latitude = models.DecimalField(max_digits=9, decimal_places=6, default=Decimal('5.520000'))
    delivery_longitude = models.DecimalField(max_digits=9, decimal_places=6, default=Decimal('5.750000'))
    max_delivery_radius_km = models.PositiveIntegerField(default=50, help_text="Maximum sourcing radius from delivery hub in km")
    status = models.CharField(max_length=32, choices=DemandStatus.choices, default=DemandStatus.OPEN, db_index=True)
    special_requirements = models.TextField(blank=True, help_text="Live delivery, minimum 1.2kg fish, gutted/chilled, etc.")

    class Meta:
        ordering = ['target_delivery_window_start']

    def __str__(self):
        return f"{self.reference_code or 'DMD'} - {self.buyer.company_name}: {self.target_volume_kg:,.0f}kg {self.enterprise_type.name}"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            short_id = str(uuid.uuid4())[:8].upper()
            self.reference_code = f"DFAC-DMD-{short_id}"
        super().save(*args, **kwargs)

    @property
    def remaining_unmatched_volume_kg(self) -> Decimal:
        return max(self.target_volume_kg - self.fulfilled_volume_kg, Decimal('0.00'))


class MatchStatus(models.TextChoices):
    PROPOSED = 'PROPOSED', 'Proposed Match'
    ACCEPTED_BY_BUYER = 'ACCEPTED_BY_BUYER', 'Accepted by Buyer'
    CONFIRMED_BY_FARMER = 'CONFIRMED_BY_FARMER', 'Confirmed by Farmer/Officer'
    CONTRACTED = 'CONTRACTED', 'Formally Contracted'
    DECLINED = 'DECLINED', 'Declined'
    FULFILLED = 'FULFILLED', 'Delivered & Fulfilled'


class ProduceMatch(TimeStampedUUIDModel):
    """Algorithmic connection between a BuyerDemand and an active ProduceBatch."""
    buyer_demand = models.ForeignKey(
        BuyerDemand,
        on_delete=models.CASCADE,
        related_name='matches'
    )
    produce_batch = models.ForeignKey(
        ProduceBatch,
        on_delete=models.CASCADE,
        related_name='matches'
    )
    allocated_volume_kg = models.DecimalField(max_digits=12, decimal_places=2)
    agreed_price_per_kg_naira = models.DecimalField(max_digits=10, decimal_places=2)
    distance_km = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal('0.00'), help_text="Computed distance between farm and off-take depot")
    status = models.CharField(max_length=32, choices=MatchStatus.choices, default=MatchStatus.PROPOSED, db_index=True)
    declined_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Match {self.reference_code or 'MCH'}: {self.allocated_volume_kg:,.0f}kg to {self.buyer_demand.buyer.company_name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            short_id = str(uuid.uuid4())[:8].upper()
            self.reference_code = f"DFAC-MCH-{short_id}"
        super().save(*args, **kwargs)

    @property
    def total_value_naira(self) -> Decimal:
        return self.allocated_volume_kg * self.agreed_price_per_kg_naira


class OfftakePaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Delivery Verification'
    ESCROW_HELD = 'ESCROW_HELD', 'Buyer Funds in Escrow'
    PAID_FARMER = 'PAID_FARMER', 'Disbursed to Smallholder / Lender Deduction'
    DISPUTED = 'DISPUTED', 'Quality / Weight Dispute'


class OfftakeTransaction(TimeStampedUUIDModel):
    """Final settlement record for harvested produce delivered to an off-taker."""
    match = models.OneToOneField(
        ProduceMatch,
        on_delete=models.CASCADE,
        related_name='offtake_transaction'
    )
    waybill_number = models.CharField(max_length=64, unique=True, db_index=True)
    actual_delivered_volume_kg = models.DecimalField(max_digits=12, decimal_places=2)
    actual_price_per_kg_naira = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount_naira = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_date = models.DateField(default=timezone.now)
    payment_status = models.CharField(max_length=32, choices=OfftakePaymentStatus.choices, default=OfftakePaymentStatus.PENDING)
    quality_inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-delivery_date']

    def __str__(self):
        return f"Off-take {self.waybill_number} - {self.actual_delivered_volume_kg:,.0f}kg (₦{self.total_amount_naira:,.2f})"

    def save(self, *args, **kwargs):
        if not self.waybill_number:
            year = timezone.now().year
            short_id = str(uuid.uuid4())[:6].upper()
            self.waybill_number = f"DFAC-WB-{year}-{short_id}"
        if not self.reference_code:
            self.reference_code = self.waybill_number
        if not self.total_amount_naira:
            self.total_amount_naira = self.actual_delivered_volume_kg * self.actual_price_per_kg_naira
        super().save(*args, **kwargs)


class CommodityPrice(TimeStampedUUIDModel):
    """Market price tracker across Niger Delta regional trading hubs."""
    enterprise_type = models.ForeignKey(
        EnterpriseType,
        on_delete=models.CASCADE,
        related_name='market_prices'
    )
    market_hub = models.CharField(max_length=128, help_text="e.g. Swali Market Yenagoa, Oil Mill Port Harcourt, Effurun Warri")
    state = models.CharField(max_length=64, default="Delta")
    price_per_kg_naira = models.DecimalField(max_digits=10, decimal_places=2)
    effective_date = models.DateField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )

    class Meta:
        ordering = ['-effective_date', 'enterprise_type']

    def __str__(self):
        return f"{self.enterprise_type.name} @ {self.market_hub} ({self.effective_date}): ₦{self.price_per_kg_naira:,.2f}/kg"
