import math
from decimal import Decimal
from django.db import models
from django.conf import settings
from django.utils import timezone
from agridep.apps.common.models import TimeStampedUUIDModel
from agridep.apps.registry.models import Farm
from agridep.apps.production.models import ProduceBatch


class FarmVisitStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'
    MISSED = 'MISSED', 'Missed / Farmer Unavailable'


class FarmVisitPurpose(models.TextChoices):
    ROUTINE_EXTENSION = 'ROUTINE_EXTENSION', 'Routine Extension & Advisory'
    BIOSECURITY_INSPECTION = 'BIOSECURITY_INSPECTION', 'Biosecurity & Water Quality Audit'
    DISEASE_INVESTIGATION = 'DISEASE_INVESTIGATION', 'Disease / Mortality Investigation'
    HARVEST_VERIFICATION = 'HARVEST_VERIFICATION', 'Pre-Harvest Yield & Grade Verification'
    LOAN_ARREARS_FOLLOWUP = 'LOAN_ARREARS_FOLLOWUP', 'Lender Credit Risk & Arrears Follow-up'
    INPUT_VERIFICATION = 'INPUT_VERIFICATION', 'Input Delivery & Application Verification'


class FarmVisit(TimeStampedUUIDModel):
    """
    Physical inspection and extension advisory visit conducted on a farm.
    Tracks GPS check-in to verify on-site presence against registered farm coordinates.
    """
    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name='visits'
    )
    officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='conducted_visits'
    )
    scheduled_date = models.DateField(default=timezone.now)
    actual_visit_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=32,
        choices=FarmVisitStatus.choices,
        default=FarmVisitStatus.SCHEDULED,
        db_index=True
    )
    purpose = models.CharField(
        max_length=32,
        choices=FarmVisitPurpose.choices,
        default=FarmVisitPurpose.ROUTINE_EXTENSION
    )
    farmer_present = models.BooleanField(default=True)
    
    # On-site GPS check-in data
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Field officer device check-in latitude (WGS84)"
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Field officer device check-in longitude (WGS84)"
    )
    gps_accuracy_meters = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('5.00'),
        help_text="Mobile device GPS fix accuracy radius"
    )
    is_geofence_verified = models.BooleanField(
        default=False,
        help_text="True if officer GPS was within the allowable drift distance of the registered farm"
    )
    distance_to_farm_meters = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Calculated distance between check-in location and registered farm coordinates"
    )

    officer_notes = models.TextField(blank=True, default='')
    farmer_feedback = models.TextField(blank=True, default='')
    linked_assignment = models.ForeignKey(
        'VisitAssignment',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='fulfilled_visits'
    )

    class Meta:
        ordering = ['-scheduled_date', '-created_at']
        indexes = [
            models.Index(fields=['farm', 'status']),
            models.Index(fields=['officer', 'status']),
        ]

    def __str__(self):
        return f"{self.reference_code or self.id} - {self.farm.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = FarmVisit.all_objects.count() + 1
            self.reference_code = f"DFAC-VST-{count:06d}"
        super().save(*args, **kwargs)


class InspectionType(models.TextChoices):
    WATER_QUALITY = 'WATER_QUALITY', 'Water Quality & Pond Chemistry'
    BIOSECURITY_AUDIT = 'BIOSECURITY_AUDIT', 'Biosecurity & Hygiene Audit'
    GROWTH_AND_FEEDING = 'GROWTH_AND_FEEDING', 'Fish Sampling & Feed Conversion Audit'
    DISEASE_ASSESSMENT = 'DISEASE_ASSESSMENT', 'Fish Pathology & Clinical Assessment'
    COMPREHENSIVE = 'COMPREHENSIVE', 'Comprehensive Full Audit'


class ComplianceRating(models.TextChoices):
    EXCELLENT = 'EXCELLENT', 'Excellent (Full Compliance)'
    SATISFACTORY = 'SATISFACTORY', 'Satisfactory (Minor Recommendations)'
    NEEDS_IMPROVEMENT = 'NEEDS_IMPROVEMENT', 'Needs Improvement (Notice Issued)'
    CRITICAL_NON_COMPLIANCE = 'CRITICAL_NON_COMPLIANCE', 'Critical Non-Compliance (Risk Flag)'


class Inspection(TimeStampedUUIDModel):
    """
    Formal quantitative audit checklist performed during a farm visit.
    Captures aquaculture water parameters (pH, DO, temp), mortality, and biosecurity scores.
    """
    visit = models.ForeignKey(
        FarmVisit,
        on_delete=models.CASCADE,
        related_name='inspections'
    )
    produce_batch = models.ForeignKey(
        ProduceBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='inspections'
    )
    inspection_type = models.CharField(
        max_length=32,
        choices=InspectionType.choices,
        default=InspectionType.WATER_QUALITY
    )
    compliance_rating = models.CharField(
        max_length=32,
        choices=ComplianceRating.choices,
        default=ComplianceRating.SATISFACTORY
    )

    # Aquaculture biometric & water parameters
    water_ph = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Water pH level (Optimal catfish range: 6.5 - 8.5)"
    )
    water_temperature_celsius = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Water temperature °C (Optimal: 26 - 32°C)"
    )
    dissolved_oxygen_mg_l = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Dissolved Oxygen (mg/L, Critical threshold < 3.0 mg/L)"
    )
    ammonia_ppm = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total ammonia nitrogen ppm (Safe: < 0.05 ppm)"
    )
    average_sample_weight_grams = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Average weight per fish from random net sampling (g)"
    )
    daily_mortality_count = models.PositiveIntegerField(
        default=0,
        help_text="Observed dead fish count on inspection day"
    )
    feed_inventory_kg = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Remaining commercial feed on farm (kg)"
    )

    # Structured questionnaire & findings
    checklist_scores = models.JSONField(
        default=dict,
        blank=True,
        help_text="Key-value audit criteria responses (e.g. {'netting_intact': true, 'inflow_screened': true})"
    )
    biosecurity_protocol_followed = models.BooleanField(default=True)
    corrective_actions = models.TextField(
        blank=True,
        default='',
        help_text="Prescribed corrective instructions for the farmer"
    )
    summary_findings = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reference_code or self.id} - {self.get_inspection_type_display()} ({self.get_compliance_rating_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = Inspection.all_objects.count() + 1
            self.reference_code = f"DFAC-INS-{count:06d}"
        super().save(*args, **kwargs)


class PhotoCategory(models.TextChoices):
    POND_WATER = 'POND_WATER', 'Pond Water Surface & Inflow'
    CROP_PLOT = 'CROP_PLOT', 'Crop Beds & Field Plot'
    SICK_FISH_SAMPLE = 'SICK_FISH_SAMPLE', 'Clinical Sample / Diseased Fish'
    FEED_STORAGE = 'FEED_STORAGE', 'Feed Bag Storage Facility'
    FARM_FACILITY = 'FARM_FACILITY', 'Farm Infrastructure & Pumping Stations'
    BIOSECURITY_EVIDENCE = 'BIOSECURITY_EVIDENCE', 'Footbath / Netting / Biosecurity'


class InspectionPhoto(TimeStampedUUIDModel):
    """
    Geotagged photographic proof captured during field inspections.
    Validated against farm GPS coordinates to prevent remote falsification.
    """
    inspection = models.ForeignKey(
        Inspection,
        on_delete=models.CASCADE,
        related_name='photos'
    )
    photo = models.FileField(
        upload_to='inspections/%Y/%m/',
        help_text="Photographic evidence file stored in S3/MinIO"
    )
    caption = models.CharField(max_length=255, blank=True, default='')
    category = models.CharField(
        max_length=32,
        choices=PhotoCategory.choices,
        default=PhotoCategory.POND_WATER
    )
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="EXIF or device captured latitude"
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="EXIF or device captured longitude"
    )
    is_geofence_verified = models.BooleanField(default=False)
    distance_to_farm_meters = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True
    )
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-captured_at']

    def __str__(self):
        return f"Photo {self.id} [{self.get_category_display()}] ({self.caption or 'Untitled'})"


class IncidentSeverity(models.TextChoices):
    LOW = 'LOW', 'Low (Informational / Minor Issue)'
    MEDIUM = 'MEDIUM', 'Medium (Sub-optimal Conditions / Minor Mortality)'
    HIGH = 'HIGH', 'High (Disease Symptoms / Water Deterioration)'
    CRITICAL = 'CRITICAL', 'Critical (Mass Mortality Outbreak / Environmental Hazard)'


class IncidentType(models.TextChoices):
    DISEASE_OUTBREAK = 'DISEASE_OUTBREAK', 'Disease Outbreak (Enteric Redmouth, Columnaris, Parasites)'
    MASS_MORTALITY = 'MASS_MORTALITY', 'Mass Mortality Event'
    WATER_CONTAMINATION = 'WATER_CONTAMINATION', 'Water Inflow Contamination / Low Oxygen'
    FEED_POISONING = 'FEED_POISONING', 'Feed Rancidity / Toxicity'
    FLOODING_EROSION = 'FLOODING_EROSION', 'Pond Dykes Overwash / Flooding'
    EQUIPMENT_FAILURE = 'EQUIPMENT_FAILURE', 'Aerator / Water Pump Breakdown'
    SECURITY_THEFT = 'SECURITY_THEFT', 'Produce Theft or Vandalism'
    OTHER = 'OTHER', 'Other Unclassified Incident'


class IncidentStatus(models.TextChoices):
    REPORTED = 'REPORTED', 'Reported (Pending Review)'
    INVESTIGATING = 'INVESTIGATING', 'Field Investigation Active'
    CONTAINED = 'CONTAINED', 'Remediation Underway'
    RESOLVED = 'RESOLVED', 'Resolved & Closed'
    DISMISSED = 'DISMISSED', 'Dismissed / False Alarm'


class IncidentReport(TimeStampedUUIDModel):
    """
    Emergency incident reported by field officers, farmers, or trainers.
    Automatically escalates high/critical incidents to farm visit assignments and financial risk flags.
    """
    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name='incident_reports'
    )
    produce_batch = models.ForeignKey(
        ProduceBatch,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='incident_reports'
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reported_incidents'
    )
    incident_type = models.CharField(
        max_length=32,
        choices=IncidentType.choices,
        default=IncidentType.DISEASE_OUTBREAK
    )
    severity = models.CharField(
        max_length=16,
        choices=IncidentSeverity.choices,
        default=IncidentSeverity.MEDIUM,
        db_index=True
    )
    status = models.CharField(
        max_length=16,
        choices=IncidentStatus.choices,
        default=IncidentStatus.REPORTED,
        db_index=True
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    immediate_actions_taken = models.TextField(blank=True, default='')
    mortality_estimate = models.PositiveIntegerField(
        default=0,
        help_text="Estimated dead fish / crop loss count"
    )
    financial_loss_estimate_ngn = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Estimated direct economic loss in ₦"
    )
    reported_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='resolved_incidents'
    )
    resolution_notes = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-reported_at']

    def __str__(self):
        return f"{self.reference_code or self.id} [{self.get_severity_display()}] - {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = IncidentReport.all_objects.count() + 1
            self.reference_code = f"DFAC-INC-{count:06d}"
        super().save(*args, **kwargs)


class AssignmentPriority(models.TextChoices):
    LOW = 'LOW', 'Low Priority'
    MEDIUM = 'MEDIUM', 'Medium Priority'
    HIGH = 'HIGH', 'High Priority'
    URGENT = 'URGENT', 'Urgent / Immediate Action Required'


class AssignmentTrigger(models.TextChoices):
    OVERDUE_ROUTINE = 'OVERDUE_ROUTINE', 'RULE-06: Farm Overdue for Routine Extension Visit'
    CRITICAL_INCIDENT = 'CRITICAL_INCIDENT', 'Emergency Incident Report'
    FINANCIAL_ARREARS = 'FINANCIAL_ARREARS', 'RULE-02: Loan Repayment Arrears Investigation'
    HARVEST_VERIFICATION = 'HARVEST_VERIFICATION', 'RULE-01: Pre-Harvest Verification & Off-take Match'
    YIELD_DEFICIT = 'YIELD_DEFICIT', 'RULE-03: Yield Deficit Early Warning Investigation'
    MANUAL_DISPATCH = 'MANUAL_DISPATCH', 'Manual Dispatch by Coordinator'


class AssignmentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Dispatch'
    ACCEPTED = 'ACCEPTED', 'Accepted by Officer'
    IN_PROGRESS = 'IN_PROGRESS', 'Visit In Progress'
    COMPLETED = 'COMPLETED', 'Visit Completed'
    REASSIGNED = 'REASSIGNED', 'Reassigned to Another Officer'
    EXPIRED = 'EXPIRED', 'Expired / Superseded'


class VisitAssignment(TimeStampedUUIDModel):
    """
    Operational dispatch order for field extension officers.
    Generated automatically by the VisitPriorityQueue decision engine or manually by supervisors.
    """
    farm = models.ForeignKey(
        Farm,
        on_delete=models.CASCADE,
        related_name='visit_assignments'
    )
    assigned_officer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='assigned_tasks'
    )
    due_date = models.DateField(default=timezone.now)
    priority_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        help_text="Calculated priority score from the dynamic multi-factor formula"
    )
    priority_level = models.CharField(
        max_length=16,
        choices=AssignmentPriority.choices,
        default=AssignmentPriority.MEDIUM,
        db_index=True
    )
    trigger_reason = models.CharField(
        max_length=32,
        choices=AssignmentTrigger.choices,
        default=AssignmentTrigger.OVERDUE_ROUTINE
    )
    status = models.CharField(
        max_length=16,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.PENDING,
        db_index=True
    )
    auto_generated = models.BooleanField(
        default=True,
        help_text="True if generated by the automated VisitPriorityQueue scanner"
    )
    scoring_breakdown = models.JSONField(
        default=dict,
        blank=True,
        help_text="Detailed points contributing to priority score (overdue, risk flags, harvest)"
    )
    instructions = models.TextField(
        blank=True,
        default='',
        help_text="Operational directions or checklist items for the visiting officer"
    )

    class Meta:
        ordering = ['-priority_score', 'due_date']
        indexes = [
            models.Index(fields=['assigned_officer', 'status']),
            models.Index(fields=['priority_level', 'status']),
        ]

    def __str__(self):
        return f"{self.reference_code or self.id} [{self.get_priority_level_display()}] - {self.farm.name} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            count = VisitAssignment.all_objects.count() + 1
            self.reference_code = f"DFAC-ASN-{count:06d}"
        super().save(*args, **kwargs)
