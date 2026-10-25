import io
import pytest
from datetime import date, timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError

from agridep.apps.registry.models import Farmer, VerificationStatus
from agridep.apps.training.models import (
    TrainingProgramme,
    TrainingSession,
    Attendance,
    AttendanceStatus,
    Assessment,
    Certificate,
    SessionStatus,
)
from agridep.apps.training.services import (
    evaluate_certification_eligibility,
    issue_certificate,
    verify_certificate_credential,
    import_bulk_attendance,
)


@pytest.fixture
def trainer_user(db):
    from agridep.apps.accounts.models import User, UserRole
    return User.objects.create_user(
        username='test_trainer',
        email='trainer@test.ng',
        password='testpassword123',
        role=UserRole.TRAINER,
        state='Delta',
        lga='Warri South'
    )


@pytest.fixture
def registered_farmer(db, delta_cohort, officer_user):
    farmer = Farmer.objects.create(
        first_name='Oghenero',
        last_name='Akpoveta',
        gender='MALE',
        state='Delta',
        lga='Warri South',
        community_address='Effurun Waterside',
        cohort=delta_cohort,
        assigned_officer=officer_user,
        phone_normalized='+2348031112233',
        verification_status=VerificationStatus.VERIFIED
    )
    farmer.set_nin('12345678901')
    farmer.save()
    return farmer


@pytest.fixture
def training_programme(db, catfish_enterprise):
    return TrainingProgramme.objects.create(
        title='Catfish Fingerling & Nursery Management',
        enterprise_type=catfish_enterprise,
        description='Intensive hands-on hatchery management and live feed production.',
        curriculum_summary='Broodstock stripping, incubation, live artemia culture.',
        duration_days=5,
        min_attendance_pct=Decimal('80.00'),
        min_pass_score=Decimal('60.00'),
        validity_months=24
    )


@pytest.fixture
def training_session(db, training_programme, trainer_user, delta_cohort):
    return TrainingSession.objects.create(
        programme=training_programme,
        trainer=trainer_user,
        cohort=delta_cohort,
        venue='DFAC Effurun Demonstration Hatchery',
        lga='Warri South',
        state='Delta',
        start_date=date.today() - timedelta(days=10),
        end_date=date.today() - timedelta(days=6),
        max_capacity=25,
        status=SessionStatus.COMPLETED
    )


@pytest.mark.django_db
def test_programme_and_session_auto_reference_codes(training_programme, training_session):
    assert training_programme.reference_code.startswith('DFAC-TRP-')
    assert training_session.reference_code.startswith('DFAC-TRS-')
    assert training_session.total_scheduled_days == 5


@pytest.mark.django_db
def test_attendance_logging_and_unique_constraint(training_session, registered_farmer, trainer_user):
    att_date = training_session.start_date
    att1 = Attendance.objects.create(
        session=training_session,
        farmer=registered_farmer,
        date=att_date,
        status=AttendanceStatus.PRESENT,
        created_by=trainer_user
    )
    assert att1.id is not None

    # Attempting to log attendance for same farmer and date in same session raises IntegrityError
    from django.db import IntegrityError
    with pytest.raises(IntegrityError):
        Attendance.objects.create(
            session=training_session,
            farmer=registered_farmer,
            date=att_date,
            status=AttendanceStatus.PRESENT
        )


@pytest.mark.django_db
def test_bulk_attendance_csv_importer(training_session, registered_farmer, trainer_user):
    csv_content = f"""session_code,farmer_code,date,status,notes
{training_session.reference_code},{registered_farmer.reference_code},{training_session.start_date},PRESENT,On-time arrival
{training_session.reference_code},{registered_farmer.reference_code},{training_session.start_date + timedelta(days=1)},PRESENT,Good participation
{training_session.reference_code},{registered_farmer.reference_code},{training_session.start_date + timedelta(days=2)},PRESENT,Practical stripping
""".encode('utf-8')

    result = import_bulk_attendance(
        file_bytes=csv_content,
        file_name='attendance_sheet.csv',
        default_session_id=training_session.id,
        recorded_by=trainer_user
    )

    assert result['imported_count'] == 3
    assert result['skipped_count'] == 0
    assert Attendance.objects.filter(session=training_session, farmer=registered_farmer).count() == 3


@pytest.mark.django_db
def test_certification_eligibility_thresholds(training_session, registered_farmer, trainer_user):
    # Case 1: Incomplete attendance (only 2 out of 5 days = 40% < 80%)
    for day in range(2):
        Attendance.objects.create(
            session=training_session,
            farmer=registered_farmer,
            date=training_session.start_date + timedelta(days=day),
            status=AttendanceStatus.PRESENT
        )

    # Assessment passed
    Assessment.objects.create(
        session=training_session,
        farmer=registered_farmer,
        score=Decimal('85.00'),
        assessor=trainer_user
    )

    eligibility = evaluate_certification_eligibility(training_session, registered_farmer)
    assert eligibility['eligible'] is False
    assert eligibility['attendance_met'] is False
    assert eligibility['assessment_met'] is True

    # Case 2: Complete remaining 3 days -> 100% attendance -> eligible!
    for day in range(2, 5):
        Attendance.objects.create(
            session=training_session,
            farmer=registered_farmer,
            date=training_session.start_date + timedelta(days=day),
            status=AttendanceStatus.PRESENT
        )

    eligibility_complete = evaluate_certification_eligibility(training_session, registered_farmer)
    assert eligibility_complete['eligible'] is True
    assert eligibility_complete['attendance_pct'] == 100.0


@pytest.mark.django_db
def test_certificate_issuance_pdf_and_qr_generation(training_session, registered_farmer, trainer_user, admin_user):
    # Setup full attendance
    for day in range(5):
        Attendance.objects.create(
            session=training_session,
            farmer=registered_farmer,
            date=training_session.start_date + timedelta(days=day),
            status=AttendanceStatus.PRESENT
        )

    # Setup passed assessment
    Assessment.objects.create(
        session=training_session,
        farmer=registered_farmer,
        score=Decimal('78.00'),
        assessor=trainer_user
    )

    cert = issue_certificate(training_session, registered_farmer, issued_by=admin_user)

    assert cert.certificate_number.startswith('DFAC-CERT-')
    assert cert.verification_code is not None
    assert bool(cert.pdf_file) is True
    assert bool(cert.qr_code_image) is True
    assert cert.is_valid is True

    # Verify credential lookup service
    verification = verify_certificate_credential(cert.certificate_number)
    assert verification['is_valid'] is True
    assert verification['details']['farmer_name'] == registered_farmer.full_name
    assert verification['details']['programme_title'] == training_session.programme.title


@pytest.mark.django_db
def test_api_certificate_verification_endpoint(api_client, training_session, registered_farmer, trainer_user, admin_user):
    for day in range(5):
        Attendance.objects.create(
            session=training_session,
            farmer=registered_farmer,
            date=training_session.start_date + timedelta(days=day),
            status=AttendanceStatus.PRESENT
        )
    Assessment.objects.create(
        session=training_session,
        farmer=registered_farmer,
        score=Decimal('90.00'),
        assessor=trainer_user
    )
    cert = issue_certificate(training_session, registered_farmer, issued_by=admin_user)

    # Query with valid token
    res = api_client.get(f'/api/v1/training/certificates/verify/?code={cert.verification_code}')
    assert res.status_code == 200
    assert res.json()['is_valid'] is True

    # Query with non-existent code
    res_invalid = api_client.get('/api/v1/training/certificates/verify/?code=INVALID-TOKEN-999')
    assert res_invalid.status_code == 404
    assert res_invalid.json()['is_valid'] is False


@pytest.mark.django_db
def test_dfac_cockpit_portal_and_geojson_view(api_client):
    # Cockpit HTML Page
    res_cockpit = api_client.get('/cockpit/')
    assert res_cockpit.status_code == 200
    assert b'DFAC Management Operational Cockpit' in res_cockpit.content
    assert b'Regional Farm Distribution' in res_cockpit.content

    # Farms GeoJSON Endpoint
    res_geojson = api_client.get('/api/farms-geojson/')
    assert res_geojson.status_code == 200
    data = res_geojson.json()
    assert data['type'] == 'FeatureCollection'
    assert 'features' in data
