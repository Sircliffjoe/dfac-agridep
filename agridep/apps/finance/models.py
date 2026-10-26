import uuid
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from agridep.apps.common.models import TimeStampedUUIDModel
from agridep.apps.registry.models import Farmer, Farm
from agridep.apps.production.models import ProductionCycle


class LenderType(models.TextChoices):
    COMMERCIAL_BANK = 'COMMERCIAL_BANK', 'Commercial Bank'
    MICROFINANCE_BANK = 'MICROFINANCE_BANK', 'Microfinance Bank (MFB)'
    DEVELOPMENT_FINANCE = 'DEVELOPMENT_FINANCE', 'Development Finance Institution (DFI)'
    COOPERATIVE = 'COOPERATIVE', 'Agricultural Cooperative Society'
    IMPACT_FUND = 'IMPACT_FUND', 'Impact / Donor Credit Fund'


class Lender(TimeStampedUUIDModel):
    """Institutional lender or microfinance provider participating in AgriDEP."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='lender_profile'
    )
    institution_name = models.CharField(max_length=128, unique=True)
    institution_type = models.CharField(max_length=32, choices=LenderType.choices, default=LenderType.MICROFINANCE_BANK)
    contact_person = models.CharField(max_length=64)
    phone = models.CharField(max_length=32)
    email = models.EmailField(blank=True, default='')
    operating_states = models.CharField(max_length=255, default="Delta, Bayelsa, Rivers")
    concessionary_rate_pct = models.DecimalField(max_digits=5, decimal_places=2, default=9.00, help_text="Benchmark annual interest rate")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['institution_name']

    def __str__(self):
        return f"{self.institution_name} ({self.get_institution_type_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            short_id = str(uuid.uuid4())[:6].upper()
            self.reference_code = f"DFAC-LND-{short_id}"
        super().save(*args, **kwargs)


class LoanStatus(models.TextChoices):
    APPLIED = 'APPLIED', 'Application Under Review'
    APPROVED = 'APPROVED', 'Credit Approved'
    DISBURSED = 'DISBURSED', 'Disbursed / Active'
    PERFORMING = 'PERFORMING', 'Performing On-Schedule'
    WATCHLIST = 'WATCHLIST', 'Watchlist (Early-Warning)'
    DELINQUENT = 'DELINQUENT', 'Delinquent / Overdue'
    REPAID = 'REPAID', 'Fully Repaid & Closed'
    WRITTEN_OFF = 'WRITTEN_OFF', 'Default / Written Off'


class LoanRecord(TimeStampedUUIDModel):
    """Primary credit facility granted to smallholders for production inputs and working capital."""
    farmer = models.ForeignKey(
        Farmer,
        on_delete=models.CASCADE,
        related_name='loans'
    )
    lender = models.ForeignKey(
        Lender,
        on_delete=models.CASCADE,
        related_name='loans'
    )
    farm = models.ForeignKey(
        Farm,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='loans'
    )
    production_cycle = models.ForeignKey(
        ProductionCycle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='loans'
    )
    facility_name = models.CharField(max_length=128, default="Smallholder Working Capital Facility")
    principal_amount_naira = models.DecimalField(max_digits=12, decimal_places=2, help_text="Total credit principal in Naira")
    interest_rate_percent = models.DecimalField(max_digits=5, decimal_places=2, default=9.00, help_text="Annualized interest percentage")
    tenure_months = models.PositiveIntegerField(default=6)
    application_date = models.DateField(default=timezone.now)
    approval_date = models.DateField(null=True, blank=True)
    disbursement_date = models.DateField(null=True, blank=True)
    repayment_due_date = models.DateField(null=True, blank=True)
    total_repaid_naira = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=32, choices=LoanStatus.choices, default=LoanStatus.APPLIED, db_index=True)
    credit_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('70.00'), help_text="Transparent rule-based score (0-100)")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference_code or 'LOAN'} - {self.farmer.full_name} (₦{self.principal_amount_naira:,.2f})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            short_id = str(uuid.uuid4())[:8].upper()
            self.reference_code = f"DFAC-LOAN-{short_id}"
        if self.disbursement_date and not self.repayment_due_date:
            from datetime import timedelta
            self.repayment_due_date = self.disbursement_date + timedelta(days=self.tenure_months * 30)
        super().save(*args, **kwargs)

    @property
    def total_payable_naira(self) -> Decimal:
        interest = self.principal_amount_naira * (self.interest_rate_percent / Decimal('100.0'))
        return self.principal_amount_naira + interest

    @property
    def outstanding_balance_naira(self) -> Decimal:
        return max(self.total_payable_naira - self.total_repaid_naira, Decimal('0.00'))


class TrancheType(models.TextChoices):
    IN_KIND_INPUTS = 'IN_KIND_INPUTS', 'In-Kind Agricultural Inputs (Fingerlings, Feed, Medication)'
    CASH_WORKING_CAPITAL = 'CASH_WORKING_CAPITAL', 'Direct Cash Working Capital (Pond Labor, Energy)'


class TrancheStatus(models.TextChoices):
    PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Stage Gate Approval'
    READY_FOR_RELEASE = 'READY_FOR_RELEASE', 'Milestone Verified - Ready for Release'
    DISBURSED = 'DISBURSED', 'Disbursed / Fulfilled'
    BLOCKED = 'BLOCKED', 'Blocked by Compliance Gate'


class LoanTranche(TimeStampedUUIDModel):
    """Staged disbursement gate enforcing in-kind delivery and pond preparation milestones."""
    loan = models.ForeignKey(
        LoanRecord,
        on_delete=models.CASCADE,
        related_name='tranches'
    )
    tranche_number = models.PositiveSmallIntegerField(default=1)
    amount_naira = models.DecimalField(max_digits=12, decimal_places=2)
    tranche_type = models.CharField(max_length=32, choices=TrancheType.choices, default=TrancheType.IN_KIND_INPUTS)
    milestone_conditions = models.TextField(help_text="Prerequisite verification criteria required to release this tranche")
    status = models.CharField(max_length=32, choices=TrancheStatus.choices, default=TrancheStatus.PENDING_APPROVAL)
    disbursement_date = models.DateField(null=True, blank=True)
    input_order_reference = models.CharField(max_length=64, blank=True, help_text="Linked input order code if in-kind")

    class Meta:
        ordering = ['loan', 'tranche_number']
        constraints = [
            models.UniqueConstraint(fields=['loan', 'tranche_number'], name='unique_loan_tranche_number')
        ]

    def __str__(self):
        return f"{self.loan.reference_code} Tranche #{self.tranche_number} (₦{self.amount_naira:,.2f}) - {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            short_id = str(uuid.uuid4())[:6].upper()
            self.reference_code = f"DFAC-TRN-{short_id}"
        super().save(*args, **kwargs)


class ScheduleStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Due Date'
    PARTIALLY_PAID = 'PARTIALLY_PAID', 'Partially Paid'
    PAID = 'PAID', 'Paid In Full'
    OVERDUE = 'OVERDUE', 'Overdue / In Arrears'


class RepaymentSchedule(TimeStampedUUIDModel):
    """Scheduled installment timeline for loan repayment."""
    loan = models.ForeignKey(
        LoanRecord,
        on_delete=models.CASCADE,
        related_name='repayment_schedules'
    )
    installment_number = models.PositiveSmallIntegerField(default=1)
    due_date = models.DateField()
    expected_amount_naira = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount_naira = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=32, choices=ScheduleStatus.choices, default=ScheduleStatus.PENDING)
    paid_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['loan', 'due_date']

    def __str__(self):
        return f"{self.loan.reference_code} Installment #{self.installment_number} Due {self.due_date}: ₦{self.expected_amount_naira:,.2f}"


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Direct NIP Transfer'
    OFFTAKE_DEDUCTION = 'OFFTAKE_DEDUCTION', 'Direct Off-take Settlement Deduction'
    CASH_DEPOSIT = 'CASH_DEPOSIT', 'Agent Cash Deposit'
    MOBILE_MONEY = 'MOBILE_MONEY', 'Mobile Money / POS'


class Repayment(TimeStampedUUIDModel):
    """Actual cash or off-take deduction remittance crediting a loan."""
    loan = models.ForeignKey(
        LoanRecord,
        on_delete=models.CASCADE,
        related_name='repayments'
    )
    schedule = models.ForeignKey(
        RepaymentSchedule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='repayments'
    )
    amount_naira = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=32, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER)
    transaction_reference = models.CharField(max_length=128, unique=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-payment_date']

    def __str__(self):
        return f"Repayment ₦{self.amount_naira:,.2f} on {self.payment_date} ({self.transaction_reference})"


class RiskSeverity(models.TextChoices):
    LOW = 'LOW', 'Low Advisory'
    MEDIUM = 'MEDIUM', 'Medium Warning (Coverage < 1.75x)'
    HIGH = 'HIGH', 'High Risk (Repayment Arrears > 7 Days)'
    CRITICAL = 'CRITICAL', 'Critical Default Risk (Coverage < 1.20x)'


class RiskFlag(TimeStampedUUIDModel):
    """Automated operational risk alert raised by the decision engine (RULE-02, RULE-03)."""
    loan = models.ForeignKey(
        LoanRecord,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='risk_flags'
    )
    farmer = models.ForeignKey(
        Farmer,
        on_delete=models.CASCADE,
        related_name='risk_flags'
    )
    production_cycle = models.ForeignKey(
        ProductionCycle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='risk_flags'
    )
    severity = models.CharField(max_length=16, choices=RiskSeverity.choices, default=RiskSeverity.MEDIUM)
    rule_triggered = models.CharField(max_length=32, help_text="e.g. RULE-02 (Arrears), RULE-03 (Yield Deficit)")
    title = models.CharField(max_length=255)
    description = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.severity}] {self.rule_triggered} - {self.title} ({self.farmer.full_name})"


class CreditRatingTier(models.TextChoices):
    EXCELLENT = 'EXCELLENT', 'Tier 1 - Excellent (Prime Concessionary)'
    GOOD = 'GOOD', 'Tier 2 - Good (Standard Concessionary)'
    MODERATE = 'MODERATE', 'Tier 3 - Moderate (Guaranteed / Co-sign)'
    HIGH_RISK = 'HIGH_RISK', 'Tier 4 - High Risk (Ineligible for Unsecured Facilities)'


class CreditScoreSnapshot(TimeStampedUUIDModel):
    """Historical and current multi-season transparent credit score assessment."""
    farmer = models.ForeignKey(
        Farmer,
        on_delete=models.CASCADE,
        related_name='credit_snapshots'
    )
    score = models.PositiveSmallIntegerField(help_text="Calculated credit score on 0-100 scale")
    rating_tier = models.CharField(max_length=32, choices=CreditRatingTier.choices, default=CreditRatingTier.MODERATE)
    
    # Pillar breakdowns (0-100 weighted contribution)
    repayment_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    biometric_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    certification_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    inspection_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    stability_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    
    recommended_credit_limit_naira = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    explanation_breakdown = models.JSONField(default=dict, blank=True)
    assessed_date = models.DateField(default=timezone.now)

    class Meta:
        ordering = ['-assessed_date', '-created_at']

    def __str__(self):
        return f"{self.farmer.first_name} {self.farmer.last_name}: {self.score}/100 [{self.get_rating_tier_display()}]"

