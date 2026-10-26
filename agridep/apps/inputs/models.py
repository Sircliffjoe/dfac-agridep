from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from agridep.apps.common.models import TimeStampedUUIDModel
from agridep.apps.registry.models import Farmer, Farm, EnterpriseType
from agridep.apps.finance.models import LoanRecord, LoanTranche


class SupplierCategory(models.TextChoices):
    AQUACULTURE_FEED = 'AQUACULTURE_FEED', 'Aquaculture Feeds (Extruded/Pellets)'
    FINGERLINGS = 'FINGERLINGS', 'Fingerlings & Broodstock (Aquaculture)'
    CASSAVA_STEMS = 'CASSAVA_STEMS', 'Certified Cassava Stems / Cuttings'
    FERTILIZER = 'FERTILIZER', 'Fertilizer & Soil Conditioners'
    VETERINARY_DRUGS = 'VETERINARY_DRUGS', 'Veterinary Medications & Water Treatments'
    EQUIPMENT = 'EQUIPMENT', 'Pumps, Aerators & Farm Equipment'
    GENERAL_AGRODEALER = 'GENERAL_AGRODEALER', 'General Agro-Dealer / Input Depot'


class OrderStatus(models.TextChoices):
    DRAFT = 'DRAFT', 'Draft Order'
    SUBMITTED = 'SUBMITTED', 'Submitted for Fulfillment'
    SUPPLIER_ACCEPTED = 'SUPPLIER_ACCEPTED', 'Accepted by Supplier'
    DISPATCHED = 'DISPATCHED', 'Dispatched for Delivery'
    DELIVERED_CONFIRMED = 'DELIVERED_CONFIRMED', 'Delivery Confirmed on Farm'
    DISPUTED = 'DISPUTED', 'Delivery Disputed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class DeliveryConfirmationChannel(models.TextChoices):
    FIELD_OFFICER_INSPECTION = 'FIELD_OFFICER_INSPECTION', 'Field Officer Geofenced Inspection'
    FARMER_SMS_OTP = 'FARMER_SMS_OTP', 'Farmer SMS / USSD OTP Confirmation'
    PORTAL_MANUAL = 'PORTAL_MANUAL', 'Portal Manual Coordinator Verification'


class InputSupplier(TimeStampedUUIDModel):
    """Verified input dealer or manufacturer in the DFAC network."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='supplier_profile'
    )
    supplier_name = models.CharField(max_length=128, unique=True)
    category = models.CharField(max_length=32, choices=SupplierCategory.choices, default=SupplierCategory.GENERAL_AGRODEALER)
    contact_name = models.CharField(max_length=64)
    phone = models.CharField(max_length=32)
    email = models.EmailField(blank=True, default='')
    state = models.CharField(max_length=64, default="Delta")
    lga = models.CharField(max_length=64, default="Warri South")
    warehouse_address = models.TextField(help_text="Primary warehouse or depot address")
    rc_number = models.CharField(max_length=32, blank=True, help_text="Corporate Affairs Commission RC/BN number")
    bank_name = models.CharField(max_length=64, blank=True)
    bank_account_number = models.CharField(max_length=10, blank=True)
    is_verified = models.BooleanField(default=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('4.50'))

    class Meta:
        ordering = ['supplier_name']

    def __str__(self):
        return f"{self.supplier_name} ({self.get_category_display()})"


class InputCatalogItem(TimeStampedUUIDModel):
    """Specific agricultural input product offered by an approved supplier."""
    supplier = models.ForeignKey(InputSupplier, on_delete=models.CASCADE, related_name='catalog_items')
    enterprise_type = models.ForeignKey(EnterpriseType, null=True, blank=True, on_delete=models.SET_NULL, related_name='input_items')
    item_name = models.CharField(max_length=128)
    item_code = models.CharField(max_length=32, unique=True, help_text="SKU or product reference")
    unit_of_measure = models.CharField(max_length=32, default="25kg Bag", help_text="e.g. 25kg Bag, 1000 Fingerlings, Bundle")
    unit_price_naira = models.DecimalField(max_digits=10, decimal_places=2)
    in_stock = models.BooleanField(default=True)
    specifications = models.TextField(blank=True, help_text="Feed crude protein %, grain size, fingerling length, etc.")

    class Meta:
        ordering = ['supplier', 'item_name']

    def __str__(self):
        return f"{self.item_name} [{self.supplier.supplier_name}] - ₦{self.unit_price_naira:,.2f}/{self.unit_of_measure}"


class InputOrder(TimeStampedUUIDModel):
    """Commercial in-kind input requisition linked to loan disbursements."""
    farmer = models.ForeignKey(Farmer, on_delete=models.CASCADE, related_name='input_orders')
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='input_orders')
    supplier = models.ForeignKey(InputSupplier, on_delete=models.CASCADE, related_name='orders')
    loan = models.ForeignKey(LoanRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name='input_orders')
    tranche = models.ForeignKey(LoanTranche, null=True, blank=True, on_delete=models.SET_NULL, related_name='linked_input_orders')
    
    order_code = models.CharField(max_length=32, unique=True, blank=True, db_index=True)
    status = models.CharField(max_length=32, choices=OrderStatus.choices, default=OrderStatus.SUBMITTED, db_index=True)
    total_amount_naira = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    ordered_at = models.DateTimeField(default=timezone.now)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    
    delivery_confirmation_channel = models.CharField(
        max_length=32,
        choices=DeliveryConfirmationChannel.choices,
        blank=True,
        default=''
    )
    delivery_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )
    delivery_notes = models.TextField(blank=True, default='')
    waybill_number = models.CharField(max_length=64, blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.order_code} - {self.farmer.first_name} {self.farmer.last_name} (₦{self.total_amount_naira:,.2f}) [{self.get_status_display()}]"

    def save(self, *args, **kwargs):
        if not self.order_code:
            import uuid
            self.order_code = f"DFAC-INP-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class InputOrderItem(TimeStampedUUIDModel):
    """Line item in an InputOrder."""
    order = models.ForeignKey(InputOrder, on_delete=models.CASCADE, related_name='items')
    catalog_item = models.ForeignKey(InputCatalogItem, on_delete=models.CASCADE, related_name='order_items')
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price_naira = models.DecimalField(max_digits=10, decimal_places=2)
    total_price_naira = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"{self.catalog_item.item_name} x {self.quantity} = ₦{self.total_price_naira:,.2f}"

    def save(self, *args, **kwargs):
        self.total_price_naira = self.quantity * self.unit_price_naira
        super().save(*args, **kwargs)
