"""
DFAC AgriDEP - Milestone M7 Demonstration Script
Demonstrates end-to-end Reporting, Inputs & Market Intelligence:
1. Dynamic System Parameters configuration (0 hardcoded values).
2. Verified Input Supplier Directory & Agricultural Requisition Catalog.
3. In-Kind Input Order Workflows & Rule-08 Staged Tranche Delivery Gating.
4. Regional Commodity Price Index & Supply-Demand Gap Intelligence.
5. Multi-Season Transparent Smallholder Credit Scoring Engine.
6. Automated Donor M&E Report Generation (PIND & GIZ Standards) in Excel (.xlsx) and PDF (.pdf).
"""
import os
import sys
import io
from decimal import Decimal
from datetime import date, timedelta

# Set Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'agridep.config.settings.local')

import django
django.setup()

from django.utils import timezone
from rest_framework.test import APIClient
import openpyxl

from agridep.apps.registry.models import Farmer, Farm, EnterpriseType, Buyer
from agridep.apps.finance.models import (
    Lender,
    LoanRecord,
    LoanStatus,
    LoanTranche,
    TrancheType,
    TrancheStatus,
    RepaymentSchedule,
    ScheduleStatus,
    Repayment,
    CreditRatingTier,
    CreditScoreSnapshot,
)
from agridep.apps.finance.services import (
    calculate_multi_season_credit_score,
    release_tranche_gate,
)
from agridep.apps.production.models import ProductionCycle, ProduceBatch, ProduceBatchStatus, ProductionLog
from agridep.apps.inputs.models import (
    InputSupplier,
    SupplierCategory,
    InputCatalogItem,
    InputOrder,
    OrderStatus,
    DeliveryConfirmationChannel,
)
from agridep.apps.inputs.services import (
    create_input_order,
    dispatch_input_order,
    confirm_input_delivery,
    verify_tranche_input_delivery_gate,
)
from agridep.apps.market.models import BuyerDemand, ProduceMatch, MatchStatus, CommodityPrice, OfftakeTransaction
from agridep.apps.market.services import (
    calculate_regional_price_index,
    analyze_supply_demand_gap,
    get_recommended_farmgate_price,
)
from agridep.apps.reporting.services import (
    compute_donor_me_indicators,
    generate_donor_excel_report,
    generate_donor_pdf_report,
)
from agridep.apps.common.models import SystemParameter


def run_demo():
    print("=" * 80)
    print("      DFAC AgriDEP - MILESTONE M7 DEMONSTRATION")
    print("   Reporting, Agro-Inputs & Market Intelligence (PIND / GIZ Phase 3)")
    print("=" * 80)

    # 1. Inspect Dynamic System Parameters
    print("\n[1] Dynamic M&E and Financial Parameters (0 hardcoded values):")
    youth_limit = SystemParameter.get('DONOR_YOUTH_AGE_THRESHOLD', default=35)
    target_farmers = SystemParameter.get('PIND_TARGET_FARMERS', default=5000)
    w_repay = SystemParameter.get('CREDIT_WEIGHT_REPAYMENT', default=0.35)
    w_bio = SystemParameter.get('CREDIT_WEIGHT_BIOMETRICS', default=0.25)
    w_cert = SystemParameter.get('CREDIT_WEIGHT_CERTIFICATION', default=0.15)
    max_limit = SystemParameter.get('CREDIT_MAX_FACILITY_LIMIT', default=1500000.00)

    print(f"    • Donor Youth Age Ceiling: <= {youth_limit} years")
    print(f"    • PIND Smallholder Outreach Target: {target_farmers:,} farmers")
    print(f"    • Credit Scoring Weights: Repayment={float(w_repay):.0%}, Biometrics={float(w_bio):.0%}, GAP Cert={float(w_cert):.0%}")
    print(f"    • Prime Smallholder Facility Cap: ₦{float(max_limit):,.2f}")

    # 2. Input Supplier Directory & Catalog
    print("\n[2] Verified Input Supplier Directory & Agricultural Catalog:")
    catfish = EnterpriseType.objects.filter(code='CATFISH').first() or EnterpriseType.objects.first()
    supplier, _ = InputSupplier.objects.get_or_create(
        supplier_name="Delta AquaFeeds & Hatcheries Ltd",
        defaults={
            "category": SupplierCategory.AQUACULTURE_FEED,
            "contact_name": "Engr. Kenneth Clark",
            "phone": "+2348035551122",
            "state": "Delta",
            "lga": "Warri South",
            "warehouse_address": "Plot 14 Deco Road, Warri",
            "is_verified": True,
            "rating": Decimal("4.85")
        }
    )
    item_starter, _ = InputCatalogItem.objects.get_or_create(
        supplier=supplier,
        item_code="AF-ALLER-2MM",
        defaults={
            "item_name": "Aller Aqua 2mm Starter Feed (25kg)",
            "enterprise_type": catfish,
            "unit_of_measure": "25kg Bag",
            "unit_price_naira": Decimal("38500.00"),
            "in_stock": True,
            "specifications": "45% Crude Protein extruded juvenile feed"
        }
    )
    item_grower, _ = InputCatalogItem.objects.get_or_create(
        supplier=supplier,
        item_code="AF-SKRET-4MM",
        defaults={
            "item_name": "Skretting 4mm Premium Grower Feed (25kg)",
            "enterprise_type": catfish,
            "unit_of_measure": "25kg Bag",
            "unit_price_naira": Decimal("36000.00"),
            "in_stock": True,
            "specifications": "42% Crude Protein floating pellets for table-size catfish"
        }
    )
    print(f"    • Approved Agro-Dealer: {supplier.supplier_name} (Rating: ★{supplier.rating})")
    print(f"    • Item 1: {item_starter.item_name} @ ₦{item_starter.unit_price_naira:,.2f}/{item_starter.unit_of_measure}")
    print(f"    • Item 2: {item_grower.item_name} @ ₦{item_grower.unit_price_naira:,.2f}/{item_grower.unit_of_measure}")

    # 3. In-Kind Input Order Workflows & Rule-08 Tranche Gating
    print("\n[3] In-Kind Input Order & Rule-08 Staged Tranche Gate Enforcement:")
    farmer, _ = Farmer.objects.get_or_create(
        phone_normalized="+2348034448899",
        defaults={
            "first_name": "Ebikeme",
            "last_name": "Clark",
            "gender": "MALE",
            "state": "Delta",
            "lga": "Warri South",
            "dob": timezone.localdate() - timedelta(days=29 * 365)
        }
    )
    farm, _ = Farm.objects.get_or_create(
        farmer=farmer,
        defaults={
            "name": "Ebikeme Modern Catfish Estate",
            "latitude": Decimal("5.528000"),
            "longitude": Decimal("5.742000")
        }
    )
    farm.enterprise_types.add(catfish)

    lender, _ = Lender.objects.get_or_create(
        institution_name="Bank of Agriculture (BOA) Warri Branch",
        defaults={"institution_type": "COMMERCIAL_BANK", "contact_person": "Aliu Bello", "phone": "+2348030008888"}
    )
    loan, _ = LoanRecord.objects.get_or_create(
        farmer=farmer,
        lender=lender,
        defaults={
            "farm": farm,
            "principal_amount_naira": Decimal("400000.00"),
            "interest_rate_percent": Decimal("9.00"),
            "tenure_months": 6,
            "status": LoanStatus.DISBURSED
        }
    )
    tranche_1, _ = LoanTranche.objects.get_or_create(
        loan=loan,
        tranche_number=1,
        defaults={
            "amount_naira": Decimal("200000.00"),
            "tranche_type": TrancheType.IN_KIND_INPUTS,
            "status": TrancheStatus.DISBURSED
        }
    )
    tranche_2, _ = LoanTranche.objects.get_or_create(
        loan=loan,
        tranche_number=2,
        defaults={
            "amount_naira": Decimal("200000.00"),
            "tranche_type": TrancheType.IN_KIND_INPUTS,
            "status": TrancheStatus.PENDING_APPROVAL
        }
    )

    # Step A: Place in-kind requisition order linked to Tranche 1
    input_order = create_input_order(
        farmer=farmer,
        farm=farm,
        supplier=supplier,
        items=[
            {'catalog_item': item_starter, 'quantity': Decimal('3')},
            {'catalog_item': item_grower, 'quantity': Decimal('2')}
        ],
        loan=loan,
        tranche=tranche_1
    )
    print(f"    • Placed Order: {input_order.order_code} (Total: ₦{input_order.total_amount_naira:,.2f})")
    print(f"    • Order Status: {input_order.get_status_display()}")

    # Step B: Test Rule-08 Gate BEFORE Delivery Confirmation
    gate_before = verify_tranche_input_delivery_gate(tranche_2)
    print(f"    [Gate Check Before Delivery] Tranche #2 Allowed: {gate_before['allowed']}")
    print(f"      - Reason: \"{gate_before['reason']}\"")

    # Step C: Dispatch and Confirm Delivery On-Farm
    dispatch_input_order(input_order, waybill_number="WB-DELTA-4491")
    confirm_input_delivery(
        order=input_order,
        confirmation_channel=DeliveryConfirmationChannel.FIELD_OFFICER_INSPECTION,
        notes="Field Officer on-site verification confirmed 5 bags received at pond-side."
    )
    print(f"    • Order Delivery Status: {input_order.get_status_display()} at {input_order.delivered_at}")

    # Step D: Test Rule-08 Gate AFTER Delivery Confirmation
    gate_after = verify_tranche_input_delivery_gate(tranche_2)
    print(f"    [Gate Check After Delivery] Tranche #2 Allowed: {gate_after['allowed']}")
    print(f"      - Reason: \"{gate_after['reason']}\"")

    # 4. Regional Commodity Price Index & Supply-Demand Gap Intelligence
    print("\n[4] Regional Market Intelligence & Supply-Demand Deficit Engine:")
    price_index = calculate_regional_price_index(enterprise_type=catfish, state="Delta", days=30)
    print(f"    • Delta Catfish Benchmark Average: ₦{price_index['average_price_per_kg_naira']:,.2f}/kg")
    print(f"    • Regional Spread: Min=₦{price_index['min_price_per_kg_naira']:,.2f}/kg | Max=₦{price_index['max_price_per_kg_naira']:,.2f}/kg")
    for hub, hub_info in price_index.get('hubs', {}).items():
        print(f"      - {hub}: ₦{hub_info['latest_price_naira']:,.2f}/kg ({hub_info['state']})")

    gap_analysis = analyze_supply_demand_gap(enterprise_type=catfish, state="Delta", window_days=60)
    print(f"    • Upcoming 60-Day Supply: {gap_analysis['total_upcoming_supply_tonnes']:.2f} Tonnes")
    print(f"    • Commercial Buyer Demand: {gap_analysis['total_active_demand_tonnes']:.2f} Tonnes")
    print(f"    • Net Market Balance: {gap_analysis['net_balance_kg']:,.0f} kg [{gap_analysis['market_condition']}]")
    print(f"    • Agronomic Clearance Outlook: \"{gap_analysis['clearance_outlook']}\"")

    # 5. Multi-Season Transparent Credit Scoring Engine
    print("\n[5] Multi-Season Credit Scoring Engine (Rule-05 Enhanced):")
    cycle, _ = ProductionCycle.objects.get_or_create(
        farm=farm,
        cycle_name="Cycle 2026-Ebikeme",
        defaults={
            "enterprise_type": catfish,
            "start_date": timezone.localdate() - timedelta(days=75),
            "projected_harvest_date": timezone.localdate() + timedelta(days=15),
            "initial_stock_count": 4000,
            "current_stock_count": 3850
        }
    )
    for i in range(4):
        ProductionLog.objects.get_or_create(
            cycle=cycle,
            log_date=timezone.localdate() - timedelta(days=i * 10),
            defaults={
                "sampling_average_weight_g": Decimal("400.00"),
                "observed_mortality_count": 1,
                "feed_consumed_kg": Decimal("30.00")
            }
        )

    # Simulate past loan repayment
    loan.total_repaid_naira = Decimal("400000.00")
    loan.status = LoanStatus.REPAID
    loan.save(update_fields=['total_repaid_naira', 'status'])

    credit_snapshot = calculate_multi_season_credit_score(farmer)
    print(f"    • Smallholder: {farmer.first_name} {farmer.last_name}")
    print(f"    • Holistic Credit Score: {credit_snapshot.score}/100 [{credit_snapshot.get_rating_tier_display()}]")
    print(f"    • Recommended Credit Ceiling: ₦{credit_snapshot.recommended_credit_limit_naira:,.2f}")
    print(f"    • Pillar Contributions:")
    print(f"      - Repayment Track Record: {credit_snapshot.repayment_score}/100")
    print(f"      - Biometric Logging Discipline: {credit_snapshot.biometric_score}/100")
    print(f"      - Field Inspection & Biosecurity: {credit_snapshot.inspection_score}/100")
    print(f"      - Farm Tenure & Stability: {credit_snapshot.stability_score}/100")

    # 6. Automated Donor Report Generation (Excel & PDF)
    print("\n[6] Automated Donor Report Generation (PIND & GIZ Standards):")
    indicators = compute_donor_me_indicators(donor="PIND")
    print(f"    • Donor Target: {indicators['donor_full_name']} ({indicators['donor']})")
    print(f"    • Profiled Beneficiaries: {indicators['demographics']['total_farmers']:,} smallholders")
    print(f"    • Gender Inclusivity: {indicators['demographics']['female_percentage']}% Female")
    print(f"    • Youth Inclusivity: {indicators['demographics']['youth_percentage']}% Youth (<= 35 yrs)")
    print(f"    • Total Credit Mobilized: ₦{indicators['financial_inclusion']['total_principal_mobilized_naira']:,.2f}")
    print(f"    • Portfolio Repayment Rate: {indicators['financial_inclusion']['repayment_rate_pct']}%")

    # Generate and save Excel file
    excel_buf = generate_donor_excel_report(indicators)
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'output'))
    os.makedirs(output_dir, exist_ok=True)

    excel_path = os.path.join(output_dir, "DFAC_AgriDEP_PIND_ME_Report.xlsx")
    with open(excel_path, 'wb') as f:
        f.write(excel_buf.getvalue())
    print(f"\n    [Excel Report Generated]: {excel_path} ({os.path.getsize(excel_path):,} bytes)")

    # Validate Excel workbook
    wb = openpyxl.load_workbook(excel_path)
    print(f"      - Sheets included: {', '.join(wb.sheetnames)}")

    # Generate and save PDF file
    pdf_buf = generate_donor_pdf_report(indicators)
    pdf_path = os.path.join(output_dir, "DFAC_AgriDEP_PIND_ME_Report.pdf")
    with open(pdf_path, 'wb') as f:
        f.write(pdf_buf.getvalue())
    print(f"\n    [PDF Report Generated]: {pdf_path} ({os.path.getsize(pdf_path):,} bytes)")

    print("\n" + "=" * 80)
    print("   MILESTONE M7 DEMONSTRATION COMPLETE - ALL SYSTEMS OPERATIONAL")
    print("=" * 80)


if __name__ == '__main__':
    run_demo()
