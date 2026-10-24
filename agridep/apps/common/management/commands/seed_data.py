from datetime import date, timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from agridep.apps.accounts.models import UserRole, ConsentRecord, StakeholderCategory, ConsentChannel
from agridep.apps.registry.models import EnterpriseType, EnterpriseCategory, Cohort, Farmer, Farm, Buyer, VerificationStatus
from agridep.apps.production.models import ProductionCycle, ProductionLog, ProduceBatch, ProduceQualityGrade, CycleStage, ProduceBatchStatus
from agridep.apps.production.services import process_production_log

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

        # 7. Cohort
        cohort_delta, _ = Cohort.objects.get_or_create(
            name='Delta Central Catfish Cohort 2026',
            defaults={
                'state': 'Delta',
                'lga': 'Warri South',
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

        self.stdout.write(self.style.SUCCESS("Demo Nigerian seed data successfully created!"))
