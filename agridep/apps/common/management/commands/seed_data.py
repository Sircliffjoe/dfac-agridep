from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from agridep.apps.accounts.models import UserRole, ConsentRecord, StakeholderCategory, ConsentChannel
from agridep.apps.registry.models import EnterpriseType, EnterpriseCategory, Cohort, Farmer, Farm, Buyer, VerificationStatus
from agridep.apps.production.models import ProductionCycle, ProductionLog, ProduceBatch, ProduceQualityGrade, CycleStage, ProduceBatchStatus
from agridep.apps.production.services import process_production_log
from agridep.apps.training.models import (
    TrainingProgramme,
    TrainingSession,
    Attendance,
    AttendanceStatus,
    Assessment,
    Certificate,
    SessionStatus,
)
from agridep.apps.training.services import issue_certificate

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds realistic Nigerian demo data across Delta, Bayelsa, and Rivers states.'

    def handle(self, *args, **options):
        self.stdout.write("Starting DFAC AgriDEP Nigerian seed data generation...")

        # 1. Superuser / DFAC Admin
        admin, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@dfac.ng',
                'role': UserRole.DFAC_ADMIN,
                'is_staff': True,
                'is_superuser': True,
                'phone_number': '+2348030000001',
                'is_phone_verified': True,
                'state': 'Delta',
                'lga': 'Warri South'
            }
        )
        admin.set_password('admin12345')
        admin.save()
        self.stdout.write("Created DFAC Admin: admin / admin12345")

        # 2. Field Officer
        officer, _ = User.objects.get_or_create(
            username='officer_delta',
            defaults={
                'email': 'officer.delta@dfac.ng',
                'role': UserRole.FIELD_OFFICER,
                'phone_number': '+2348030000002',
                'is_phone_verified': True,
                'state': 'Delta',
                'lga': 'Warri South'
            }
        )
        officer.set_password('password123')
        officer.save()

        # 3. Trainer
        trainer, _ = User.objects.get_or_create(
            username='trainer_john',
            defaults={
                'email': 'trainer.john@dfac.ng',
                'role': UserRole.TRAINER,
                'phone_number': '+2348030000003',
                'is_phone_verified': True,
                'state': 'Delta',
                'lga': 'Ughelli North'
            }
        )
        trainer.set_password('password123')
        trainer.save()

        # 4. Lender
        lender_user, _ = User.objects.get_or_create(
            username='lender_bank',
            defaults={
                'email': 'agri.credit@nigerbank.ng',
                'role': UserRole.LENDER,
                'phone_number': '+2348030000004',
                'is_phone_verified': True,
                'state': 'Rivers',
                'lga': 'Port Harcourt'
            }
        )
        lender_user.set_password('password123')
        lender_user.save()

        # 5. Buyer
        buyer_user, _ = User.objects.get_or_create(
            username='buyer_aggregator',
            defaults={
                'email': 'procurement@nigerdeltafish.ng',
                'role': UserRole.BUYER,
                'phone_number': '+2348030000005',
                'is_phone_verified': True,
                'state': 'Rivers',
                'lga': 'Port Harcourt'
            }
        )
        buyer_user.set_password('password123')
        buyer_user.save()

        # 6. Enterprise Types
        catfish, _ = EnterpriseType.objects.get_or_create(
            code='CATFISH',
            defaults={
                'name': 'African Catfish (Clarias gariepinus)',
                'category': EnterpriseCategory.AQUACULTURE,
                'standard_cycle_days': 150,
                'benchmark_fcr': Decimal('1.25'),
                'expected_mortality_rate_pct': Decimal('7.50'),
                'reference_price_per_kg_naira': Decimal('2600.00'),
            }
        )
        tilapia, _ = EnterpriseType.objects.get_or_create(
            code='TILAPIA',
            defaults={
                'name': 'Nile Tilapia (Oreochromis niloticus)',
                'category': EnterpriseCategory.AQUACULTURE,
                'standard_cycle_days': 180,
                'benchmark_fcr': Decimal('1.40'),
                'expected_mortality_rate_pct': Decimal('6.00'),
                'reference_price_per_kg_naira': Decimal('2200.00'),
            }
        )
        cassava, _ = EnterpriseType.objects.get_or_create(
            code='CASSAVA',
            defaults={
                'name': 'High-Yield Cassava (TME 419)',
                'category': EnterpriseCategory.CROPS,
                'standard_cycle_days': 300,
                'benchmark_fcr': Decimal('0.0'),
                'expected_mortality_rate_pct': Decimal('3.00'),
                'reference_price_per_kg_naira': Decimal('450.00'),
            }
        )
        poultry, _ = EnterpriseType.objects.get_or_create(
            code='POULTRY',
            defaults={
                'name': 'Broiler Poultry',
                'category': EnterpriseCategory.LIVESTOCK,
                'standard_cycle_days': 56,
                'benchmark_fcr': Decimal('1.70'),
                'expected_mortality_rate_pct': Decimal('4.00'),
                'reference_price_per_kg_naira': Decimal('3200.00'),
            }
        )
        snail, _ = EnterpriseType.objects.get_or_create(
            code='SNAIL',
            defaults={
                'name': 'Giant African Land Snail (Archachatina marginata)',
                'category': EnterpriseCategory.LIVESTOCK,
                'standard_cycle_days': 240,
                'benchmark_fcr': Decimal('2.00'),
                'expected_mortality_rate_pct': Decimal('5.00'),
                'reference_price_per_kg_naira': Decimal('4500.00'),
            }
        )

        # 7. Cohort
        cohort_delta, _ = Cohort.objects.get_or_create(
            name='Delta Central Catfish Cohort 2026',
            defaults={
                'state': 'Delta',
                'lga': 'Warri South',
                'lead_officer': officer
            }
        )
        cohort_bayelsa, _ = Cohort.objects.get_or_create(
            name='Bayelsa Aquaculture & Snail Hub',
            defaults={
                'state': 'Bayelsa',
                'lga': 'Yenagoa',
                'lead_officer': officer
            }
        )

        # 8. Buyer profile
        buyer_profile, _ = Buyer.objects.get_or_create(
            company_name='Niger Delta Fish Processors Ltd',
            defaults={
                'user': buyer_user,
                'rc_number': 'RC-1498322',
                'contact_name': 'Chief Kenneth Ovie',
                'phone': '+2348030000005',
                'email': 'procurement@nigerdeltafish.ng',
                'tier': 'PROCESSOR',
                'operating_states': 'Delta, Bayelsa, Rivers'
            }
        )

        # 9. Realistic Farmers & Farms
        farmers_data = [
            {
                'first_name': 'Ebuka',
                'last_name': 'Okoro',
                'gender': 'MALE',
                'phone': '+2348031112233',
                'nin': '12345678901',
                'state': 'Delta',
                'lga': 'Warri South',
                'community': 'Ogunu Waterway Area',
                'farm_name': 'Okoro Aquaculture Enterprise',
                'lat': 5.544230,
                'lon': 5.760269,
                'ponds': 6,
                'area_ha': Decimal('0.80'),
                'stock': 4000
            },
            {
                'first_name': 'Preye',
                'last_name': 'Diri',
                'gender': 'FEMALE',
                'phone': '+2348032223344',
                'nin': '23456789012',
                'state': 'Bayelsa',
                'lga': 'Yenagoa',
                'community': 'Swali Waterfront',
                'farm_name': 'Swali River Ponds',
                'lat': 4.926710,
                'lon': 6.267640,
                'ponds': 4,
                'area_ha': Decimal('0.50'),
                'stock': 3000
            },
            {
                'first_name': 'Tamuno',
                'last_name': 'Briggs',
                'gender': 'MALE',
                'phone': '+2348033334455',
                'nin': '34567890123',
                'state': 'Rivers',
                'lga': 'Port Harcourt',
                'community': 'Alakahia Creek',
                'farm_name': 'Briggs Integrated Fisheries',
                'lat': 4.815640,
                'lon': 7.049840,
                'ponds': 8,
                'area_ha': Decimal('1.20'),
                'stock': 6000
            }
        ]

        for item in farmers_data:
            farmer, _ = Farmer.objects.get_or_create(
                phone_normalized=item['phone'],
                defaults={
                    'first_name': item['first_name'],
                    'last_name': item['last_name'],
                    'gender': item['gender'],
                    'state': item['state'],
                    'lga': item['lga'],
                    'community_address': item['community'],
                    'cohort': cohort_delta,
                    'assigned_officer': officer,
                    'verification_status': VerificationStatus.VERIFIED
                }
            )
            farmer.set_nin(item['nin'])
            farmer.save()

            # NDPA Consent
            ConsentRecord.objects.get_or_create(
                farmer_reference=farmer.reference_code,
                stakeholder_category=StakeholderCategory.ALL_ECOSYSTEM,
                defaults={
                    'consent_given': True,
                    'consent_scope': 'Consent granted to DFAC AgriDEP for financing and off-take linkages',
                    'channel': ConsentChannel.MOBILE_APP,
                    'captured_by': officer
                }
            )

            # Farm
            farm, _ = Farm.objects.get_or_create(
                farmer=farmer,
                name=item['farm_name'],
                defaults={
                    'latitude': item['lat'],
                    'longitude': item['lon'],
                    'community': item['community'],
                    'number_of_ponds': item['ponds'],
                    'total_area_hectares': item['area_ha'],
                    'water_source': 'BOREHOLE'
                }
            )
            farm.enterprise_types.add(catfish)

            # Production Cycle
            start_dt = date.today() - timedelta(days=130)
            cycle, _ = ProductionCycle.objects.get_or_create(
                farm=farm,
                cycle_name=f"{item['first_name']} Catfish Cycle 1",
                defaults={
                    'enterprise_type': catfish,
                    'start_date': start_dt,
                    'projected_harvest_date': start_dt + timedelta(days=150),
                    'initial_stock_count': item['stock'],
                    'current_stock_count': item['stock'] - 120,
                    'initial_average_weight_g': Decimal('12.0'),
                    'current_average_weight_g': Decimal('850.0'),
                    'status': CycleStage.GROWING
                }
            )

            # Production Log
            log, _ = ProductionLog.objects.get_or_create(
                cycle=cycle,
                log_date=date.today() - timedelta(days=2),
                defaults={
                    'sampling_average_weight_g': Decimal('880.0'),
                    'observed_mortality_count': 5,
                    'feed_consumed_kg': Decimal('45.0'),
                    'water_temperature_c': Decimal('28.5'),
                    'ph_level': Decimal('7.3'),
                    'dissolved_oxygen_ppm': Decimal('5.8'),
                    'notes': 'Fish feeding actively. Sampling shows rapid weight gain towards table size.'
                }
            )
            process_production_log(log)

        # -------------------------------------------------------------
        # Milestone M2: Capacity Building Programmes & Certifications
        # -------------------------------------------------------------
        self.stdout.write("Seeding Milestone M2 Training Programmes and Accreditation...")

        prog_catfish, _ = TrainingProgramme.objects.get_or_create(
            title="Commercial Catfish Hatchery & Fingerling Management",
            defaults={
                'enterprise_type': catfish,
                'description': "Comprehensive training on broodstock selection, induced spawning, hatching biosecurity, and nursery feeding.",
                'curriculum_summary': "1. Broodstock Hormone Conditioning\n2. Incubation & Water Quality Monitoring\n3. Live Feed (Artemia) Management\n4. Grading & Cannibalism Prevention",
                'duration_days': 5,
                'min_attendance_pct': Decimal('80.00'),
                'min_pass_score': Decimal('60.00'),
                'validity_months': 24,
                'is_active': True
            }
        )

        prog_ras, _ = TrainingProgramme.objects.get_or_create(
            title="Modern Recirculating Aquaculture Systems (RAS) & Water Chemistry",
            defaults={
                'enterprise_type': catfish,
                'description': "Advanced biofiltration, mechanical solids removal, aeration optimization, and ammonia nitrification cycle management.",
                'curriculum_summary': "1. Biological Filter Inoculation\n2. Dissolved Oxygen & Nitrite Control\n3. High-Density Stocking Economics\n4. Power Redundancy Systems",
                'duration_days': 7,
                'min_attendance_pct': Decimal('85.00'),
                'min_pass_score': Decimal('65.00'),
                'validity_months': 24,
                'is_active': True
            }
        )

        prog_snail, _ = TrainingProgramme.objects.get_or_create(
            title="Intensive Commercial Snail Farming & Snailery Design",
            defaults={
                'enterprise_type': snail,
                'description': "Archachatina marginata breeding, paddock greenhouse design, calcium soil conditioning, and pest exclusion.",
                'curriculum_summary': "1. Paddock Microclimate Control\n2. Soil Treatment & Calcium Fortification\n3. Incubation Box Moisture Management\n4. Snail Slime Harvest & Hygiene",
                'duration_days': 4,
                'min_attendance_pct': Decimal('75.00'),
                'min_pass_score': Decimal('60.00'),
                'validity_months': 24,
                'is_active': True
            }
        )

        prog_poultry, _ = TrainingProgramme.objects.get_or_create(
            title="Smallholder Broiler Biosecurity & Feed Formulation",
            defaults={
                'enterprise_type': poultry,
                'description': "Brooding temperatures, Gumboro/Newcastle vaccination timing, on-farm feed mixing, and litter management.",
                'curriculum_summary': "1. Brooder House Setup\n2. Vaccination Administration via Drinking Water\n3. Feed Conversion Ratio (FCR) Optimization\n4. Mortality Disposal Protocols",
                'duration_days': 5,
                'min_attendance_pct': Decimal('80.00'),
                'min_pass_score': Decimal('60.00'),
                'validity_months': 24,
                'is_active': True
            }
        )

        # Create Training Sessions
        sess_warri, _ = TrainingSession.objects.get_or_create(
            programme=prog_catfish,
            venue="DFAC Fisheries Demonstration Farm, Effurun-Warri",
            defaults={
                'trainer': trainer,
                'cohort': cohort_delta,
                'lga': "Warri South",
                'state': "Delta",
                'start_date': date.today() - timedelta(days=20),
                'end_date': date.today() - timedelta(days=16),
                'max_capacity': 25,
                'status': SessionStatus.COMPLETED,
                'notes': "Intensive 5-day fingerling production masterclass with hands-on hatchery stripping."
            }
        )

        sess_yenagoa, _ = TrainingSession.objects.get_or_create(
            programme=prog_ras,
            venue="Bayelsa State Agricultural Training Centre, Yenagoa",
            defaults={
                'trainer': trainer,
                'cohort': cohort_bayelsa,
                'lga': "Yenagoa",
                'state': "Bayelsa",
                'start_date': date.today() - timedelta(days=12),
                'end_date': date.today() - timedelta(days=6),
                'max_capacity': 30,
                'status': SessionStatus.COMPLETED,
                'notes': "Biofiltration and dissolved oxygen monitoring workshop for Niger Delta flood plains."
            }
        )

        sess_ughelli, _ = TrainingSession.objects.get_or_create(
            programme=prog_snail,
            venue="Ughelli North Demonstration Farm, Agbarho",
            defaults={
                'trainer': trainer,
                'cohort': cohort_delta,
                'lga': "Ughelli North",
                'state': "Delta",
                'start_date': date.today() - timedelta(days=2),
                'end_date': date.today() + timedelta(days=2),
                'max_capacity': 20,
                'status': SessionStatus.IN_PROGRESS,
                'notes': "Hands-on greenhouse paddock construction."
            }
        )

        # Log Attendance and Assessments for Seed Farmers
        all_farmers = list(Farmer.objects.filter(is_deleted=False))
        if all_farmers:
            # Trainee 1: Emmanuel (full attendance, high score -> Cert issued)
            f_emmanuel = all_farmers[0]
            for day_offset in range(5):
                Attendance.objects.get_or_create(
                    session=sess_warri,
                    farmer=f_emmanuel,
                    date=sess_warri.start_date + timedelta(days=day_offset),
                    defaults={'status': AttendanceStatus.PRESENT, 'created_by': trainer}
                )
            Assessment.objects.get_or_create(
                session=sess_warri,
                farmer=f_emmanuel,
                defaults={
                    'score': Decimal('88.50'),
                    'max_score': Decimal('100.00'),
                    'passed': True,
                    'assessor': trainer,
                    'assessment_date': sess_warri.end_date,
                    'feedback': "Demonstrated exceptional mastery of pituitary gland extraction and egg fertilization."
                }
            )
            # Generate official certificate
            try:
                cert1 = issue_certificate(sess_warri, f_emmanuel, issued_by=admin)
                self.stdout.write(f"Issued accredited certificate: {cert1.certificate_number} to {f_emmanuel.full_name}")
            except Exception as e:
                self.stdout.write(f"Certificate note: {e}")

            # Trainee 2: Ebiere (full attendance at Yenagoa RAS session -> Cert issued)
            if len(all_farmers) > 1:
                f_ebiere = all_farmers[1]
                for day_offset in range(7):
                    Attendance.objects.get_or_create(
                        session=sess_yenagoa,
                        farmer=f_ebiere,
                        date=sess_yenagoa.start_date + timedelta(days=day_offset),
                        defaults={'status': AttendanceStatus.PRESENT, 'created_by': trainer}
                    )
                Assessment.objects.get_or_create(
                    session=sess_yenagoa,
                    farmer=f_ebiere,
                    defaults={
                        'score': Decimal('92.00'),
                        'max_score': Decimal('100.00'),
                        'passed': True,
                        'assessor': trainer,
                        'assessment_date': sess_yenagoa.end_date,
                        'feedback': "Mastered water quality testing kits and biofilter backwash sequencing."
                    }
                )
                try:
                    cert2 = issue_certificate(sess_yenagoa, f_ebiere, issued_by=admin)
                    self.stdout.write(f"Issued accredited certificate: {cert2.certificate_number} to {f_ebiere.full_name}")
                except Exception as e:
                    self.stdout.write(f"Certificate note: {e}")

        self.stdout.write(self.style.SUCCESS("Demo Nigerian seed data successfully created!"))
