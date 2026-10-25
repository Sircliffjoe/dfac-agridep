import io
import csv
import uuid
from datetime import datetime, date
from decimal import Decimal
import qrcode
from PIL import Image

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.utils import timezone
from django.conf import settings

from agridep.apps.training.models import (
    TrainingProgramme,
    TrainingSession,
    Attendance,
    AttendanceStatus,
    Assessment,
    Certificate,
    SessionStatus,
)
from agridep.apps.registry.models import Farmer
from agridep.apps.audit.services import log_audit_event
from agridep.apps.common.encryption import hash_deterministic


def evaluate_certification_eligibility(session: TrainingSession, farmer: Farmer) -> dict:
    """
    Evaluates whether a smallholder farmer has met the mandatory capacity-building
    criteria (attendance threshold + competency score) to receive an accredited certificate.
    """
    programme = session.programme
    
    # 1. Calculate attendance rate
    # Session total scheduled days
    total_days = session.total_scheduled_days
    attended_count = Attendance.objects.filter(
        session=session,
        farmer=farmer,
        status=AttendanceStatus.PRESENT
    ).count()

    attendance_pct = (attended_count / max(total_days, 1)) * 100.0

    # 2. Assessment scoring
    assessment = Assessment.objects.filter(session=session, farmer=farmer).first()
    has_assessment = assessment is not None
    score = float(assessment.score) if assessment else 0.0
    passed = assessment.passed if assessment else False

    # 3. Check thresholds
    min_attendance = float(programme.min_attendance_pct)
    min_score = float(programme.min_pass_score)

    attendance_met = attendance_pct >= min_attendance
    assessment_met = has_assessment and (passed or score >= min_score)

    reasons = []
    if not attendance_met:
        reasons.append(
            f"Attendance rate {attendance_pct:.1f}% is below required {min_attendance:.1f}% ({attended_count}/{total_days} days attended)."
        )
    if not has_assessment:
        reasons.append("Competency assessment has not been recorded.")
    elif not assessment_met:
        reasons.append(
            f"Assessment score {score:.1f} is below minimum passing mark {min_score:.1f}."
        )

    is_eligible = attendance_met and assessment_met

    return {
        'eligible': is_eligible,
        'attendance_pct': round(attendance_pct, 1),
        'attended_days': attended_count,
        'total_days': total_days,
        'attendance_met': attendance_met,
        'has_assessment': has_assessment,
        'score': round(score, 1),
        'min_score': min_score,
        'assessment_met': assessment_met,
        'reasons': reasons,
    }


def generate_qr_code_image(verification_url: str):
    """Generates a high-contrast QR code image and returns (ContentFile, PIL.Image)."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(verification_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F5132", back_color="white")  # DFAC forest green on white
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    raw_bytes = buf.getvalue()
    return ContentFile(raw_bytes, name="qr_code.png"), img


def render_certificate_pdf(certificate: Certificate, base_url: str = "http://localhost:8000") -> ContentFile:
    """
    Renders an executive, security-grade A4 Landscape PDF certificate
    with Doctor Fish branding, decorative borders, and dynamic QR verification.
    """
    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)
    
    # Generate verification QR Code image
    verification_url = f"{base_url.rstrip('/')}/portal/verify-certificate/{certificate.verification_code}/"
    qr_content, qr_img = generate_qr_code_image(verification_url)
    
    # Save QR code into certificate model field
    qr_filename = f"qr_{certificate.verification_code[:12]}.png"
    certificate.qr_code_image.save(qr_filename, qr_content, save=False)

    p = canvas.Canvas(buffer, pagesize=landscape(A4))
    
    # --- Decorative Security Border ---
    # Outer dark forest green border
    p.setStrokeColor(colors.HexColor("#0B3D2E"))
    p.setLineWidth(5)
    p.rect(20, 20, page_width - 40, page_height - 40)
    
    # Inner gold border
    p.setStrokeColor(colors.HexColor("#D4AF37"))
    p.setLineWidth(1.5)
    p.rect(26, 26, page_width - 52, page_height - 52)

    # Corner ornamental accents
    corner_size = 18
    p.setFillColor(colors.HexColor("#0B3D2E"))
    for x, y in [(26, 26), (page_width - 26 - corner_size, 26), 
                 (26, page_height - 26 - corner_size), (page_width - 26 - corner_size, page_height - 26 - corner_size)]:
        p.rect(x, y, corner_size, corner_size, fill=1, stroke=0)

    # --- Header Section ---
    p.setFont("Helvetica-Bold", 14)
    p.setFillColor(colors.HexColor("#0B3D2E"))
    p.drawCentredString(page_width / 2.0, page_height - 65, "DOCTOR FISH AGRICULTURAL CONSULT (DFAC)")
    
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.HexColor("#555555"))
    p.drawCentredString(page_width / 2.0, page_height - 80, "DFAC Agricultural Data Ecosystem Platform (AgriDEP) • Capacity Building Directorate")
    
    p.setStrokeColor(colors.HexColor("#D4AF37"))
    p.setLineWidth(1)
    p.line(page_width / 2.0 - 150, page_height - 90, page_width / 2.0 + 150, page_height - 90)

    # Title of Certificate
    p.setFont("Helvetica-Bold", 24)
    p.setFillColor(colors.HexColor("#0F5132"))
    p.drawCentredString(page_width / 2.0, page_height - 130, "CERTIFICATE OF ACCREDITATION")

    p.setFont("Helvetica-Oblique", 11)
    p.setFillColor(colors.HexColor("#444444"))
    p.drawCentredString(page_width / 2.0, page_height - 155, "This is to certify that smallholder agricultural producer")

    # Recipient Farmer Name
    p.setFont("Helvetica-Bold", 26)
    p.setFillColor(colors.HexColor("#1A202C"))
    farmer_name = certificate.farmer.full_name.upper()
    p.drawCentredString(page_width / 2.0, page_height - 195, farmer_name)
    
    # Farmer reference & LGA
    p.setFont("Helvetica", 10)
    p.setFillColor(colors.HexColor("#6B7280"))
    farmer_meta = f"Farmer ID: {certificate.farmer.reference_code or 'N/A'} • {certificate.farmer.lga}, {certificate.farmer.state} State"
    p.drawCentredString(page_width / 2.0, page_height - 212, farmer_meta)

    # Completion Body Text
    p.setFont("Helvetica", 11)
    p.setFillColor(colors.HexColor("#374151"))
    p.drawCentredString(
        page_width / 2.0, 
        page_height - 245, 
        "has successfully demonstrated required operational competency and completed the approved curriculum in:"
    )

    # Programme Title
    p.setFont("Helvetica-Bold", 17)
    p.setFillColor(colors.HexColor("#0B3D2E"))
    p.drawCentredString(page_width / 2.0, page_height - 275, certificate.programme.title)

    # Training Session Metadata
    session = certificate.session
    session_text = f"Conducted at: {session.venue}, {session.lga}, {session.state} • Period: {session.start_date.strftime('%d %b %Y')} to {session.end_date.strftime('%d %b %Y')}"
    p.setFont("Helvetica-Oblique", 10)
    p.setFillColor(colors.HexColor("#555555"))
    p.drawCentredString(page_width / 2.0, page_height - 298, session_text)

    # --- Footer & Verification Details ---
    # Draw QR Code image in bottom left
    qr_x = 55
    qr_y = 50
    qr_w = 75
    qr_h = 75
    p.drawInlineImage(qr_img, qr_x, qr_y, width=qr_w, height=qr_h)
    
    p.setFont("Helvetica-Bold", 8)
    p.setFillColor(colors.HexColor("#0B3D2E"))
    p.drawString(qr_x + qr_w + 12, qr_y + 60, "VERIFIABLE CREDENTIAL")
    
    p.setFont("Helvetica", 7.5)
    p.setFillColor(colors.HexColor("#4B5563"))
    p.drawString(qr_x + qr_w + 12, qr_y + 46, f"Certificate No: {certificate.certificate_number}")
    p.drawString(qr_x + qr_w + 12, qr_y + 34, f"Verification Token: {certificate.verification_code[:16]}...")
    p.drawString(qr_x + qr_w + 12, qr_y + 22, f"Issued: {certificate.issue_date.strftime('%d %b %Y')} • Expires: {certificate.expiry_date.strftime('%d %b %Y') if certificate.expiry_date else 'Permanent'}")
    p.drawString(qr_x + qr_w + 12, qr_y + 10, "Scan QR code or visit DFAC portal to verify authentic accreditation.")

    # Signatures
    # Signatory 1: Lead Technical Trainer
    sig1_x = page_width - 290
    p.setStrokeColor(colors.HexColor("#9CA3AF"))
    p.setLineWidth(1)
    p.line(sig1_x, 90, sig1_x + 100, 90)
    p.setFont("Helvetica-Bold", 9)
    p.setFillColor(colors.HexColor("#1F2937"))
    p.drawCentredString(sig1_x + 50, 78, "Lead Assessor")
    p.setFont("Helvetica", 7.5)
    p.setFillColor(colors.HexColor("#6B7280"))
    p.drawCentredString(sig1_x + 50, 66, "DFAC Training Faculty")

    # Signatory 2: Managing Director
    sig2_x = page_width - 150
    p.line(sig2_x, 90, sig2_x + 100, 90)
    p.setFont("Helvetica-Bold", 9)
    p.setFillColor(colors.HexColor("#1F2937"))
    p.drawCentredString(sig2_x + 50, 78, "Managing Consultant")
    p.setFont("Helvetica", 7.5)
    p.setFillColor(colors.HexColor("#6B7280"))
    p.drawCentredString(sig2_x + 50, 66, "Doctor Fish Consult")

    p.showPage()
    p.save()

    buffer.seek(0)
    pdf_filename = f"cert_{certificate.certificate_number.replace('/', '_')}.pdf"
    return ContentFile(buffer.getvalue(), name=pdf_filename)


@transaction.atomic
def issue_certificate(
    session: TrainingSession, 
    farmer: Farmer, 
    issued_by=None, 
    base_url: str = "http://localhost:8000",
    force: bool = False
) -> Certificate:
    """
    Validates smallholder eligibility against session criteria and generates
    the official accreditation certificate with embedded QR and PDF.
    """
    eligibility = evaluate_certification_eligibility(session, farmer)
    if not eligibility['eligible'] and not force:
        reason_str = " | ".join(eligibility['reasons'])
        raise ValidationError(f"Farmer {farmer.full_name} is not eligible for certification: {reason_str}")

    # Check if certificate already exists
    cert = Certificate.objects.filter(
        farmer=farmer,
        programme=session.programme,
        session=session
    ).first()

    if not cert:
        cert = Certificate(
            farmer=farmer,
            programme=session.programme,
            session=session,
            issue_date=timezone.now().date(),
            created_by=issued_by,
        )
        cert.save()

    # Render PDF & QR Code
    pdf_file = render_certificate_pdf(cert, base_url=base_url)
    cert.pdf_file.save(pdf_file.name, pdf_file, save=True)

    # Log audit event for NDPA accreditation record
    log_audit_event(
        action="ISSUE_CERTIFICATE",
        resource_type="Certificate",
        resource_id=str(cert.id),
        user=issued_by,
        details={
            "certificate_number": cert.certificate_number,
            "farmer_id": str(farmer.id),
            "farmer_name": farmer.full_name,
            "programme": session.programme.title,
            "attendance_pct": eligibility['attendance_pct'],
            "score": eligibility['score'],
        }
    )

    return cert


def verify_certificate_credential(query_code: str) -> dict:
    """
    Verifies a certificate using either its human-readable certificate number
    (e.g. DFAC-CERT-2026-...) or its cryptographic verification token.
    """
    clean_code = query_code.strip()
    cert = Certificate.objects.filter(
        models.Q(certificate_number__iexact=clean_code) |
        models.Q(verification_code__iexact=clean_code)
    ).select_related('farmer', 'programme', 'session').first()

    if not cert:
        return {
            'is_valid': False,
            'status': 'NOT_FOUND',
            'message': 'Certificate not found. No record matches the provided credential.',
            'certificate': None,
            'details': {}
        }

    is_expired = cert.expiry_date and cert.expiry_date < timezone.now().date()
    status = "VALID" if (cert.is_valid and not is_expired) else ("EXPIRED" if is_expired else "REVOKED")

    return {
        'is_valid': cert.is_valid and not is_expired,
        'status': status,
        'certificate': cert,
        'details': {
            'certificate_number': cert.certificate_number,
            'farmer_name': cert.farmer.full_name,
            'farmer_code': cert.farmer.reference_code,
            'farmer_state': cert.farmer.state,
            'farmer_lga': cert.farmer.lga,
            'programme_title': cert.programme.title,
            'enterprise_type': cert.programme.enterprise_type.name if cert.programme.enterprise_type else "General Agribusiness",
            'training_venue': f"{cert.session.venue}, {cert.session.lga}",
            'issue_date': cert.issue_date.strftime('%d %B %Y'),
            'expiry_date': cert.expiry_date.strftime('%d %B %Y') if cert.expiry_date else 'Permanent',
            'session_period': f"{cert.session.start_date.strftime('%d %b %Y')} to {cert.session.end_date.strftime('%d %b %Y')}",
        }
    }


def parse_date_flexible(date_str: str) -> date:
    """Parses various date formats from CSV/Excel into Python date."""
    if isinstance(date_str, (datetime, date)):
        return date_str.date() if isinstance(date_str, datetime) else date_str
    
    clean_str = str(date_str).strip()
    formats = [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%m/%d/%Y',
        '%Y/%m/%d',
        '%d %b %Y',
        '%d %B %Y'
    ]
    for fmt in formats:
        try:
            return datetime.strptime(clean_str, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unable to parse date string: '{date_str}'")


def import_bulk_attendance(
    file_bytes: bytes, 
    file_name: str, 
    default_session_id=None,
    recorded_by=None
) -> dict:
    """
    Parses legacy CSV or Excel (.xlsx) attendance sheets and imports
    them into DFAC AgriDEP idempotently.
    
    Expected Columns (case-insensitive):
    - session_code / session_id (optional if default_session_id is passed)
    - farmer_code / phone / nin / farmer_id
    - date (YYYY-MM-DD or DD/MM/YYYY)
    - status (PRESENT / ABSENT / EXCUSED or P/A/E or 1/0)
    - notes (optional)
    """
    rows = []
    
    if file_name.lower().endswith('.csv'):
        text_stream = io.StringIO(file_bytes.decode('utf-8-sig', errors='replace'))
        reader = csv.DictReader(text_stream)
        for r in reader:
            rows.append({k.strip().lower(): v.strip() for k, v in r.items() if k})
    elif file_name.lower().endswith(('.xlsx', '.xls')):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        sheet = wb.active
        headers = [str(cell.value or '').strip().lower() for cell in sheet[1]]
        for row_cells in sheet.iter_rows(min_row=2, values_only=True):
            if any(row_cells):
                row_dict = {}
                for idx, header in enumerate(headers):
                    if header and idx < len(row_cells):
                        val = row_cells[idx]
                        row_dict[header] = str(val).strip() if val is not None else ''
                rows.append(row_dict)
    else:
        raise ValidationError("Unsupported file format. Please upload a CSV (.csv) or Excel (.xlsx) file.")

    imported_count = 0
    skipped_count = 0
    errors = []

    # Cache farmers and sessions to optimize bulk lookups
    all_farmers_by_ref = {f.reference_code: f for f in Farmer.objects.all() if f.reference_code}
    all_farmers_by_id = {str(f.id): f for f in Farmer.objects.all()}
    
    # Also index by phone_normalized and nin_hash
    all_farmers_by_phone = {f.phone_normalized: f for f in Farmer.objects.all() if f.phone_normalized}
    all_farmers_by_nin_hash = {f.nin_hash: f for f in Farmer.objects.all() if f.nin_hash}

    all_sessions_by_ref = {s.reference_code: s for s in TrainingSession.objects.all() if s.reference_code}
    all_sessions_by_id = {str(s.id): s for s in TrainingSession.objects.all()}

    default_session = None
    if default_session_id:
        default_session = TrainingSession.objects.filter(
            models.Q(id=default_session_id) | models.Q(reference_code=str(default_session_id))
        ).first()

    for row_idx, row in enumerate(rows, start=2):
        try:
            # 1. Resolve Session
            session = None
            session_ref = row.get('session_code') or row.get('session_id') or row.get('session')
            if session_ref:
                session = all_sessions_by_ref.get(session_ref) or all_sessions_by_id.get(session_ref)
            if not session:
                session = default_session

            if not session:
                errors.append(f"Row {row_idx}: Could not resolve training session '{session_ref or 'default'}'.")
                skipped_count += 1
                continue

            # 2. Resolve Farmer
            farmer = None
            farmer_ref = (
                row.get('farmer_code') or 
                row.get('farmer_id') or 
                row.get('farmer') or
                row.get('reference_code')
            )
            phone_val = row.get('phone') or row.get('phone_number') or row.get('farmer_phone')

            if farmer_ref:
                farmer = all_farmers_by_ref.get(farmer_ref) or all_farmers_by_id.get(farmer_ref)
            
            if not farmer and phone_val:
                # Normalize phone and match
                clean_phone = phone_val.replace(' ', '').replace('-', '').replace('+', '')
                if clean_phone.startswith('0'):
                    clean_phone = '234' + clean_phone[1:]
                elif not clean_phone.startswith('234'):
                    clean_phone = '234' + clean_phone
                formatted_phone = '+' + clean_phone
                farmer = all_farmers_by_phone.get(formatted_phone)

            if not farmer:
                errors.append(f"Row {row_idx}: Farmer '{farmer_ref or phone_val}' not found in registry.")
                skipped_count += 1
                continue

            # 3. Resolve Date
            raw_date = row.get('date') or row.get('attendance_date') or str(timezone.now().date())
            att_date = parse_date_flexible(raw_date)

            # 4. Resolve Status
            raw_status = (row.get('status') or 'PRESENT').strip().upper()
            status_map = {
                'PRESENT': AttendanceStatus.PRESENT,
                'P': AttendanceStatus.PRESENT,
                '1': AttendanceStatus.PRESENT,
                'YES': AttendanceStatus.PRESENT,
                'TRUE': AttendanceStatus.PRESENT,
                'ABSENT': AttendanceStatus.ABSENT,
                'A': AttendanceStatus.ABSENT,
                '0': AttendanceStatus.ABSENT,
                'NO': AttendanceStatus.ABSENT,
                'FALSE': AttendanceStatus.ABSENT,
                'EXCUSED': AttendanceStatus.EXCUSED,
                'E': AttendanceStatus.EXCUSED,
            }
            status = status_map.get(raw_status, AttendanceStatus.PRESENT)
            notes = row.get('notes', '')

            # 5. Idempotent Upsert
            attendance, created = Attendance.objects.update_or_create(
                session=session,
                farmer=farmer,
                date=att_date,
                defaults={
                    'status': status,
                    'notes': notes,
                    'created_by': recorded_by,
                }
            )
            imported_count += 1

        except Exception as exc:
            errors.append(f"Row {row_idx}: {str(exc)}")
            skipped_count += 1

    return {
        'total_rows': len(rows),
        'imported_count': imported_count,
        'skipped_count': skipped_count,
        'errors': errors[:20],  # truncate first 20 errors for readability
    }
