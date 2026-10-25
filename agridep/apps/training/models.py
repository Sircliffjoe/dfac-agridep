import uuid
from datetime import timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from agridep.apps.common.models import TimeStampedUUIDModel
from agridep.apps.registry.models import EnterpriseType, Cohort, Farmer

class TrainingProgramme(TimeStampedUUIDModel):
    """Curriculum definition for smallholder capacity building."""
    title = models.CharField(max_length=255, help_text="e.g. Modern Catfish Nursery & Hatchery Management")
    enterprise_type = models.ForeignKey(
        EnterpriseType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_programmes'
    )
    description = models.TextField(blank=True)
    curriculum_summary = models.TextField(blank=True, help_text="Outline of modules and key competency outcomes")
    duration_days = models.PositiveIntegerField(default=5, help_text="Standard duration in days")
    min_attendance_pct = models.DecimalField(max_digits=5, decimal_places=2, default=80.00, help_text="Minimum attendance required to qualify for certificate")
    min_pass_score = models.DecimalField(max_digits=5, decimal_places=2, default=60.00, help_text="Minimum competency assessment score (0-100)")
    validity_months = models.PositiveIntegerField(default=24, help_text="Certificate validity period in months")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return f"{self.reference_code or 'TRP'} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            short_uuid = str(uuid.uuid4())[:6].upper()
            self.reference_code = f"DFAC-TRP-{short_uuid}"
        super().save(*args, **kwargs)


class SessionStatus(models.TextChoices):
    SCHEDULED = 'SCHEDULED', 'Scheduled'
    IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class TrainingSession(TimeStampedUUIDModel):
    """An instantiated cohort training delivery event at a physical location."""
    programme = models.ForeignKey(
        TrainingProgramme,
        on_delete=models.CASCADE,
        related_name='sessions'
    )
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='training_sessions'
    )
    cohort = models.ForeignKey(
        Cohort,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='training_sessions'
    )
    venue = models.CharField(max_length=255, help_text="Facility, farm demonstration centre or LGA secretariat")
    lga = models.CharField(max_length=64, default="Warri South")
    state = models.CharField(max_length=64, default="Delta")
    start_date = models.DateField()
    end_date = models.DateField()
    max_capacity = models.PositiveIntegerField(default=30)
    status = models.CharField(max_length=32, choices=SessionStatus.choices, default=SessionStatus.SCHEDULED)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.reference_code or 'TRS'} - {self.programme.title} ({self.venue}, {self.lga})"

    def save(self, *args, **kwargs):
        if not self.reference_code:
            short_uuid = str(uuid.uuid4())[:6].upper()
            self.reference_code = f"DFAC-TRS-{short_uuid}"
        super().save(*args, **kwargs)

    @property
    def total_scheduled_days(self):
        if self.start_date and self.end_date:
            return max((self.end_date - self.start_date).days + 1, 1)
        return self.programme.duration_days


class AttendanceStatus(models.TextChoices):
    PRESENT = 'PRESENT', 'Present'
    ABSENT = 'ABSENT', 'Absent'
    EXCUSED = 'EXCUSED', 'Excused'


class Attendance(TimeStampedUUIDModel):
    """Daily check-in / biometric sign-in record for a smallholder at a session."""
    session = models.ForeignKey(
        TrainingSession,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    farmer = models.ForeignKey(
        Farmer,
        on_delete=models.CASCADE,
        related_name='attendances'
    )
    date = models.DateField()
    status = models.CharField(max_length=16, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-date', 'farmer__last_name']
        constraints = [
            models.UniqueConstraint(fields=['session', 'farmer', 'date'], name='unique_session_farmer_date')
        ]

    def __str__(self):
        return f"{self.farmer} - {self.session.reference_code} on {self.date}: {self.get_status_display()}"


class Assessment(TimeStampedUUIDModel):
    """Post-training competency and practical field demonstration scoring."""
    session = models.ForeignKey(
        TrainingSession,
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    farmer = models.ForeignKey(
        Farmer,
        on_delete=models.CASCADE,
        related_name='assessments'
    )
    score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="Score achieved (e.g. 78.50)")
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=100.00)
    passed = models.BooleanField(default=False)
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+'
    )
    assessment_date = models.DateField(default=timezone.now)
    feedback = models.TextField(blank=True, help_text="Trainer remarks on biosecurity, water management or feeding discipline")

    class Meta:
        ordering = ['-assessment_date']
        constraints = [
            models.UniqueConstraint(fields=['session', 'farmer'], name='unique_session_farmer_assessment')
        ]

    def __str__(self):
        return f"{self.farmer} Assessment: {self.score}/{self.max_score} ({'PASS' if self.passed else 'FAIL'})"

    def save(self, *args, **kwargs):
        # Automatically update pass/fail based on programme criteria
        if self.session and self.session.programme:
            min_score = self.session.programme.min_pass_score
            self.passed = self.score >= min_score
        super().save(*args, **kwargs)


class Certificate(TimeStampedUUIDModel):
    """Official credential issued to smallholders completing DFAC capacity building."""
    certificate_number = models.CharField(max_length=64, unique=True, db_index=True)
    verification_code = models.CharField(max_length=64, unique=True, db_index=True, help_text="Cryptographic or UUID token for instant QR verification")
    farmer = models.ForeignKey(
        Farmer,
        on_delete=models.CASCADE,
        related_name='certificates'
    )
    programme = models.ForeignKey(
        TrainingProgramme,
        on_delete=models.CASCADE,
        related_name='certificates'
    )
    session = models.ForeignKey(
        TrainingSession,
        on_delete=models.CASCADE,
        related_name='certificates'
    )
    issue_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(null=True, blank=True)
    is_valid = models.BooleanField(default=True, db_index=True)
    pdf_file = models.FileField(upload_to='certificates/pdfs/', null=True, blank=True)
    qr_code_image = models.FileField(upload_to='certificates/qrcodes/', null=True, blank=True)

    class Meta:
        ordering = ['-issue_date']
        constraints = [
            models.UniqueConstraint(fields=['farmer', 'programme', 'session'], name='unique_farmer_programme_session_cert')
        ]

    def __str__(self):
        return f"Certificate {self.certificate_number} - {self.farmer.full_name} ({self.programme.title})"

    def save(self, *args, **kwargs):
        current_year = timezone.now().year
        if not self.certificate_number:
            short_id = str(uuid.uuid4())[:8].upper()
            self.certificate_number = f"DFAC-CERT-{current_year}-{short_id}"
        if not self.reference_code:
            self.reference_code = self.certificate_number
        if not self.verification_code:
            self.verification_code = uuid.uuid4().hex
        if not self.expiry_date and self.programme and self.programme.validity_months:
            self.expiry_date = self.issue_date + timedelta(days=self.programme.validity_months * 30)
        super().save(*args, **kwargs)
