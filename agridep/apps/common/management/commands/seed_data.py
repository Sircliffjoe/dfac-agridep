from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from agridep.apps.common.models import SystemParameter
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
from agridep.apps.finance.models import (
    Lender,
    LenderType,
    LoanRecord,
    LoanStatus,
    LoanTranche,
    TrancheType,
    TrancheStatus,
    RepaymentSchedule,
    ScheduleStatus,
    Repayment,
    RiskFlag,
    RiskSeverity,
)
from agridep.apps.finance.services import (
    disburse_loan_facility,
    calculate_loan_expected_value_and_risk,
)
from agridep.apps.market.models import (
    BuyerDemand,
    DemandStatus,
    ProduceMatch,
    MatchStatus,
    OfftakeTransaction,
    OfftakePaymentStatus,
    CommodityPrice,
)
from agridep.apps.inputs.models import (
    InputSupplier,
    SupplierCategory,
    InputCatalogItem,
    InputOrder,
    OrderStatus,
)
from agridep.apps.inputs.services import create_input_order, confirm_input_delivery
from agridep.apps.market.services import (
    propose_buyer_matches_for_demand,
    confirm_produce_match,
)
from agridep.apps.fieldops.models import (
    FarmVisit,
    FarmVisitStatus,
    FarmVisitPurpose,
    Inspection,
    InspectionType,
    ComplianceRating,
    IncidentReport,
    IncidentSeverity,
    IncidentType,
    VisitAssignment,
)
from agridep.apps.fieldops.services import (
    log_farm_visit,
    report_incident,
    auto_generate_visit_assignments,
)
from agridep.apps.alerts.models import AlertRule, AlertNotification, AlertChannel, AlertPriority, AlertStatus
from agridep.apps.alerts.services import send_transactional_sms, notify_harvest_readiness
from agridep.apps.market.models import CommodityPrice
from agridep.apps.common.parameters import seed_system_parameters

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds realistic Nigerian demo data across Delta, Bayelsa, and Rivers states.'

    def handle(self, *args, **options):
        self.stdout.write("Starting DFAC AgriDEP Nigerian seed data generation...")

        # 0. Seed dynamic system parameters
        params_created = seed_system_parameters()
        self.stdout.write(f"Seeded {params_created} dynamic system parameters into database.")

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

        # -------------------------------------------------------------
        # Milestone M3: Finance, Credit Portfolios & Market Linkages
        # -------------------------------------------------------------
        self.stdout.write("Seeding Milestone M3 Finance and Market Off-take Networks...")

        # 1. Institutional Lender
        lender_inst, _ = Lender.objects.get_or_create(
            institution_name='Niger Delta Agricultural Credit Bank (NDACB)',
            defaults={
                'user': lender_user,
                'institution_type': LenderType.DEVELOPMENT_FINANCE,
                'contact_person': 'Mrs. Chinyere Nwosu',
                'phone': '+2348030000004',
                'email': 'agri.credit@nigerbank.ng',
                'operating_states': 'Delta, Bayelsa, Rivers',
                'concessionary_rate_pct': Decimal('9.00'),
                'is_active': True
            }
        )

        # 2. Benchmark Regional Commodity Prices
        CommodityPrice.objects.get_or_create(
            enterprise_type=catfish,
            market_hub="Effurun Fish Market, Warri",
            defaults={'state': 'Delta', 'price_per_kg_naira': Decimal('2600.00'), 'recorded_by': officer}
        )
        CommodityPrice.objects.get_or_create(
            enterprise_type=catfish,
            market_hub="Swali Regional Market, Yenagoa",
            defaults={'state': 'Bayelsa', 'price_per_kg_naira': Decimal('2550.00'), 'recorded_by': officer}
        )
        CommodityPrice.objects.get_or_create(
            enterprise_type=snail,
            market_hub="Agbarho Snail & Bushmeat Hub, Ughelli",
            defaults={'state': 'Delta', 'price_per_kg_naira': Decimal('4500.00'), 'recorded_by': officer}
        )
        CommodityPrice.objects.get_or_create(
            enterprise_type=poultry,
            market_hub="Oil Mill Regional Market, Port Harcourt",
            defaults={'state': 'Rivers', 'price_per_kg_naira': Decimal('3200.00'), 'recorded_by': officer}
        )

        # 3. Transparent Loan Facility (₦200,000 Loan against ₦850,000 Harvest Model)
        f_pere = all_farmers[0] if all_farmers else None
        if f_pere:
            pere_farm = f_pere.farms.first()
            pere_cycle = pere_farm.production_cycles.first() if pere_farm else None

            loan1, _ = LoanRecord.objects.get_or_create(
                farmer=f_pere,
                facility_name="Smallholder Catfish Working Capital Facility",
                defaults={
                    'lender': lender_inst,
                    'farm': pere_farm,
                    'production_cycle': pere_cycle,
                    'principal_amount_naira': Decimal('200000.00'),
                    'interest_rate_percent': Decimal('9.00'),
                    'tenure_months': 6,
                    'credit_score': Decimal('85.00'),
                    'status': LoanStatus.DISBURSED,
                    'application_date': date.today() - timedelta(days=60),
                    'approval_date': date.today() - timedelta(days=50),
                    'disbursement_date': date.today() - timedelta(days=45),
                    'total_repaid_naira': Decimal('36333.33'),
                    'notes': "Concessionary facility benchmarked against ₦850,000 projected harvest value."
                }
            )

            # Create Tranches (RULE-08 staging)
            LoanTranche.objects.get_or_create(
                loan=loan1,
                tranche_number=1,
                defaults={
                    'amount_naira': Decimal('120000.00'),
                    'tranche_type': TrancheType.IN_KIND_INPUTS,
                    'milestone_conditions': 'Delivery of 5,000 fingerlings and 15 bags starter feed confirmed',
                    'status': TrancheStatus.DISBURSED,
                    'disbursement_date': date.today() - timedelta(days=45),
                    'input_order_reference': 'DFAC-INP-0012'
                }
            )
            LoanTranche.objects.get_or_create(
                loan=loan1,
                tranche_number=2,
                defaults={
                    'amount_naira': Decimal('80000.00'),
                    'tranche_type': TrancheType.CASH_WORKING_CAPITAL,
                    'milestone_conditions': 'Month 2 biometric water sampling & growth sampling confirmed',
                    'status': TrancheStatus.READY_FOR_RELEASE
                }
            )

            # Evaluate expected value & risk
            risk_eval = calculate_loan_expected_value_and_risk(loan1)
            self.stdout.write(
                f"Loan {loan1.reference_code}: Principal ₦{loan1.principal_amount_naira:,.2f} vs "
                f"Harvest ₦{risk_eval['expected_harvest_value']:,.2f} (Coverage: {risk_eval['coverage_ratio']}x)"
            )

        # 4. Buyer Commercial Purchase Demand (5 Tonnes Catfish by Month Y)
        demand_warri, _ = BuyerDemand.objects.get_or_create(
            buyer=buyer_profile,
            enterprise_type=catfish,
            target_volume_kg=Decimal('5000.00'),
            defaults={
                'offered_price_per_kg_naira': Decimal('2600.00'),
                'minimum_grade': ProduceQualityGrade.GRADE_A,
                'target_delivery_window_start': date.today() + timedelta(days=5),
                'target_delivery_window_end': date.today() + timedelta(days=25),
                'delivery_state': "Delta",
                'delivery_lga': "Warri South",
                'delivery_address': "Plot 14 NPA Expressway, Industrial Layout, Warri",
                'delivery_latitude': Decimal('5.524000'),
                'delivery_longitude': Decimal('5.748000'),
                'max_delivery_radius_km': 65,
                'status': DemandStatus.OPEN,
                'special_requirements': "Minimum table size 800g-1.2kg live catfish, live transport tanks provided."
            }
        )

        # 5. Algorithmic Match Allocation (RULE-04)
        matches = propose_buyer_matches_for_demand(demand_warri)
        if matches:
            self.stdout.write(f"Matched {len(matches)} producer batch(es) to {buyer_profile.company_name} ({demand_warri.fulfilled_volume_kg:,.0f}kg allocated)")
            # Confirm first match to demonstrate Contracted Off-take and Waybill
            offtake = confirm_produce_match(matches[0], confirmed_by=admin)
            self.stdout.write(f"Confirmed Off-take Contract: Waybill #{offtake.waybill_number} for {offtake.actual_delivered_volume_kg:,.0f}kg (₦{offtake.total_amount_naira:,.2f})")

        # -------------------------------------------------------------
        # 6. Milestone M4: Field Operations, Inspections & Geofencing
        # -------------------------------------------------------------
        self.stdout.write("Seeding Milestone M4 Field Operations, Inspections & Priority Queues...")

        farm_alagoa = Farm.objects.filter(farmer__last_name='Alagoa').first()
        farm_agidee = Farm.objects.filter(farmer__last_name='Agidee').first()

        if farm_alagoa:
            # Completed visit with verified geofence (on-site GPS)
            visit1, created = FarmVisit.objects.get_or_create(
                farm=farm_alagoa,
                status=FarmVisitStatus.COMPLETED,
                defaults={
                    'officer': officer,
                    'scheduled_date': date.today() - timedelta(days=12),
                    'actual_visit_date': timezone.now() - timedelta(days=12),
                    'purpose': FarmVisitPurpose.BIOSECURITY_INSPECTION,
                    'farmer_present': True,
                    'latitude': farm_alagoa.latitude,
                    'longitude': farm_alagoa.longitude,
                    'gps_accuracy_meters': Decimal('4.20'),
                    'is_geofence_verified': True,
                    'distance_to_farm_meters': Decimal('8.50'),
                    'officer_notes': "Water chemistry optimal. Netting intact across all 4 operational earthen ponds.",
                    'farmer_feedback': "Requested advisory on fingerling grading technique for next cycle."
                }
            )
            if created:
                Inspection.objects.get_or_create(
                    visit=visit1,
                    defaults={
                        'inspection_type': InspectionType.WATER_QUALITY,
                        'compliance_rating': ComplianceRating.EXCELLENT,
                        'water_ph': Decimal('7.40'),
                        'water_temperature_celsius': Decimal('28.5'),
                        'dissolved_oxygen_mg_l': Decimal('6.20'),
                        'ammonia_ppm': Decimal('0.02'),
                        'average_sample_weight_grams': Decimal('850.00'),
                        'daily_mortality_count': 1,
                        'feed_inventory_kg': Decimal('450.00'),
                        'biosecurity_protocol_followed': True,
                        'summary_findings': "Pond dissolved oxygen levels excellent. Recommended continued twice-daily aeration."
                    }
                )
                self.stdout.write(f"Logged verified visit {visit1.reference_code} for {farm_alagoa.name}")

        if farm_agidee:
            # Active emergency incident report triggering urgent priority
            incident1, created = IncidentReport.objects.get_or_create(
                farm=farm_agidee,
                title="Pond 2 Inflow Turbidity & Low Dissolved Oxygen Warning",
                defaults={
                    'reported_by': officer,
                    'incident_type': IncidentType.WATER_CONTAMINATION,
                    'severity': IncidentSeverity.HIGH,
                    'status': 'REPORTED',
                    'description': "Heavy rainfall runoff caused mud siltation in inlet canal. Morning DO measured 2.8 mg/L with surface piping.",
                    'immediate_actions_taken': "Activated backup gasoline aerator pump and suspended evening feeding.",
                    'mortality_estimate': 15,
                    'financial_loss_estimate_ngn': Decimal('35000.00')
                }
            )
            if created:
                self.stdout.write(f"Logged emergency incident {incident1.reference_code} for {farm_agidee.name}")

        # Run automated decision engine priority queue auto-dispatch
        dispatched = auto_generate_visit_assignments(officer=officer)
        self.stdout.write(f"Decision Engine generated {len(dispatched)} prioritized field visit assignments.")

        # -------------------------------------------------------------
        # 7. Milestone M6: SMS & USSD Telecom Engagement Channel
        # -------------------------------------------------------------
        self.stdout.write("Seeding Milestone M6 SMS, USSD & Alert Notification Rules...")

        # Commodity Price Indices for USSD Price Menu
        catfish_type = EnterpriseType.objects.filter(code='CATFISH').first() or EnterpriseType.objects.first()
        if catfish_type:
            CommodityPrice.objects.get_or_create(
                enterprise_type=catfish_type,
                market_hub="Effurun Main Market, Warri",
                defaults={
                    'state': "Delta",
                    'price_per_kg_naira': Decimal('2600.00'),
                    'effective_date': date.today()
                }
            )
            CommodityPrice.objects.get_or_create(
                enterprise_type=catfish_type,
                market_hub="Swali International Market, Yenagoa",
                defaults={
                    'state': "Bayelsa",
                    'price_per_kg_naira': Decimal('2550.00'),
                    'effective_date': date.today()
                }
            )
            CommodityPrice.objects.get_or_create(
                enterprise_type=catfish_type,
                market_hub="Oil Mill Market, Port Harcourt",
                defaults={
                    'state': "Rivers",
                    'price_per_kg_naira': Decimal('2700.00'),
                    'effective_date': date.today()
                }
            )

        # Core Alert Rules
        rule_harvest, _ = AlertRule.objects.get_or_create(
            rule_code="RULE_01_HARVEST",
            defaults={
                'name': "Pre-Harvest Readiness Alert",
                'description': "Sent when produce batch reaches 14-day pre-harvest window",
                'channel': AlertChannel.SMS,
                'priority': AlertPriority.HIGH,
                'message_template': "Hello {farmer_name}, your catfish batch on {farm_name} is projected harvest-ready in {days} days. Dial *384*223# to review buyer off-take offers."
            }
        )

        rule_repay, _ = AlertRule.objects.get_or_create(
            rule_code="RULE_02_ARREARS",
            defaults={
                'name': "Loan Repayment Arrears Warning",
                'description': "Dispatched when loan repayment is 7 days past due",
                'channel': AlertChannel.SMS,
                'priority': AlertPriority.HIGH,
                'message_template': "DFAC Notice: Loan {loan_ref} has an overdue balance of NGN {balance}. Dial *384*223# for repayment options."
            }
        )

        # Dispatch sample transactional SMS to Tari Agidee & Pere Alagoa
        farmer_tari = Farmer.objects.filter(last_name='Agidee').first()
        if farmer_tari and farmer_tari.phone_normalized:
            send_transactional_sms(
                phone_number=farmer_tari.phone_normalized,
                message=f"DFAC AgriDEP: Welcome {farmer_tari.first_name}! Dial *384*223# on any phone to check loans, report mortality, or accept buyer offers.",
                priority=AlertPriority.NORMAL,
                user=farmer_tari.user
            )
            self.stdout.write(f"Dispatched welcome SMS to {farmer_tari.phone_normalized}")

        # -------------------------------------------------------------
        # 8. Milestone M7: Reporting, Inputs & Market Intelligence
        # -------------------------------------------------------------
        self.stdout.write("Seeding Milestone M7 Input Suppliers & Catalogs...")

        # Verified Input Agro-Dealers
        supplier_feed, _ = InputSupplier.objects.get_or_create(
            supplier_name="Delta AquaFeeds & Hatcheries Ltd",
            defaults={
                'category': SupplierCategory.AQUACULTURE_FEED,
                'contact_name': "Engr. Kenneth Clark",
                'phone': "+2348035551122",
                'email': "supplies@deltaaquafeeds.ng",
                'state': "Delta",
                'lga': "Warri South",
                'warehouse_address': "Plot 14 Deco Road, Warri Industrial Zone",
                'rc_number': "RC-884920",
                'bank_name': "Zenith Bank",
                'bank_account_number': "1012345678",
                'is_verified': True,
                'rating': Decimal('4.80')
            }
        )

        supplier_agro, _ = InputSupplier.objects.get_or_create(
            supplier_name="Niger Delta Integrated Agro-Hub",
            defaults={
                'category': SupplierCategory.GENERAL_AGRODEALER,
                'contact_name': "Mrs. Blessing Okoro",
                'phone': "+2348024449988",
                'email': "info@nd-agrohub.ng",
                'state': "Delta",
                'lga': "Ughelli North",
                'warehouse_address': "12 Market Road, Ughelli",
                'rc_number': "RC-992144",
                'bank_name': "Access Bank",
                'bank_account_number': "0098765432",
                'is_verified': True,
                'rating': Decimal('4.60')
            }
        )

        # Catalog Items
        item_feed_2mm, _ = InputCatalogItem.objects.get_or_create(
            supplier=supplier_feed,
            item_code="AF-ALLER-2MM",
            defaults={
                'item_name': "Aller Aqua 2mm Starter Pellets (25kg)",
                'enterprise_type': catfish_type,
                'unit_of_measure': "25kg Bag",
                'unit_price_naira': Decimal('38500.00'),
                'in_stock': True,
                'specifications': "45% Crude Protein extruded sinking feed for juvenile catfish."
            }
        )

        item_feed_4mm, _ = InputCatalogItem.objects.get_or_create(
            supplier=supplier_feed,
            item_code="AF-SKRET-4MM",
            defaults={
                'item_name': "Skretting 4mm Premium Grower Feed (25kg)",
                'enterprise_type': catfish_type,
                'unit_of_measure': "25kg Bag",
                'unit_price_naira': Decimal('36000.00'),
                'in_stock': True,
                'specifications': "42% Crude Protein extruded floating feed for table-size catfish."
            }
        )

        item_fingerlings, _ = InputCatalogItem.objects.get_or_create(
            supplier=supplier_agro,
            item_code="CL-FING-1000",
            defaults={
                'item_name': "High-Vigor Clarias Fingerlings (1,000 pcs)",
                'enterprise_type': catfish_type,
                'unit_of_measure': "1,000 Fingerlings",
                'unit_price_naira': Decimal('45000.00'),
                'in_stock': True,
                'specifications': "7-10cm graded healthy Clarias Gariepinus fingerlings, disease-free."
            }
        )

        # Seed sample in-kind input order linked to Tari Agidee's loan
        loan_tari = LoanRecord.objects.filter(farmer__last_name='Agidee').first()
        farm_tari = Farm.objects.filter(farmer__last_name='Agidee').first()
        if loan_tari and farm_tari and loan_tari.tranches.exists():
            tranche_1 = loan_tari.tranches.filter(tranche_number=1).first()
            if tranche_1 and not InputOrder.objects.filter(tranche=tranche_1).exists():
                order = create_input_order(
                    farmer=loan_tari.farmer,
                    farm=farm_tari,
                    supplier=supplier_feed,
                    items=[
                        {'catalog_item': item_feed_2mm, 'quantity': Decimal('4')},
                        {'catalog_item': item_feed_4mm, 'quantity': Decimal('6')}
                    ],
                    loan=loan_tari,
                    tranche=tranche_1
                )
                confirm_input_delivery(
                    order=order,
                    confirmation_channel="FIELD_OFFICER_INSPECTION",
                    notes="Physical pond-side inspection verified 10 bags delivered."
                )
                self.stdout.write(f"Created & confirmed sample InputOrder {order.order_code} (₦{order.total_amount_naira:,.2f})")

        self.stdout.write(self.style.SUCCESS("Demo Nigerian seed data successfully created!"))
