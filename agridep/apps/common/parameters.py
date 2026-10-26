from decimal import Decimal
from agridep.apps.common.models import SystemParameter, ParameterCategory, ParameterDataType

DEFAULT_PARAMETERS = [
    # Field Operations & Priority Queue
    {
        'key': 'fieldops_priority_w1_overdue_weight',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Priority W1: Overdue Days Weight',
        'description': 'Points added per day past the baseline visit threshold (default: 1.0 point/day).',
        'value': '1.00',
        'default_value': '1.00',
    },
    {
        'key': 'fieldops_overdue_threshold_days',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.INTEGER,
        'label': 'Priority Queue Overdue Threshold (Days)',
        'description': 'Number of days since last visit before a farm starts accumulating overdue priority points (default: 30 days).',
        'value': '30',
        'default_value': '30',
    },
    {
        'key': 'fieldops_overdue_max_days_cap',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.INTEGER,
        'label': 'Priority Queue Overdue Days Cap',
        'description': 'Maximum overdue days counted towards w1 priority points to prevent runaway scores (default: 90 days).',
        'value': '90',
        'default_value': '90',
    },
    {
        'key': 'fieldops_priority_w2_critical_risk_points',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Priority W2: Critical Risk Points',
        'description': 'Priority points added for each active CRITICAL financial risk flag on the farm.',
        'value': '50.00',
        'default_value': '50.00',
    },
    {
        'key': 'fieldops_priority_w2_high_risk_points',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Priority W2: High Risk Points',
        'description': 'Priority points added for each active HIGH financial risk flag on the farm.',
        'value': '30.00',
        'default_value': '30.00',
    },
    {
        'key': 'fieldops_priority_w2_medium_risk_points',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Priority W2: Medium Risk Points',
        'description': 'Priority points added for each active MEDIUM financial risk flag on the farm.',
        'value': '15.00',
        'default_value': '15.00',
    },
    {
        'key': 'fieldops_priority_w2_low_risk_points',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Priority W2: Low Risk Points',
        'description': 'Priority points added for each active LOW financial risk flag on the farm.',
        'value': '5.00',
        'default_value': '5.00',
    },
    {
        'key': 'fieldops_priority_w3_harvest_days_threshold',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.INTEGER,
        'label': 'Priority W3: Harvest Proximity Window (Days)',
        'description': 'Number of days before projected harvest date within which pre-harvest inspection points apply (default: 10 days).',
        'value': '10',
        'default_value': '10',
    },
    {
        'key': 'fieldops_priority_w3_harvest_score',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Priority W3: Harvest Urgency Score',
        'description': 'Priority score awarded when a farm batch is within the pre-harvest inspection window (default: 40.0 points).',
        'value': '40.00',
        'default_value': '40.00',
    },
    {
        'key': 'fieldops_priority_w4_incident_points',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Priority W4: Unresolved Incident Score',
        'description': 'Priority points added for each open or investigating disease, mortality, or environmental incident.',
        'value': '30.00',
        'default_value': '30.00',
    },
    {
        'key': 'fieldops_rule06_unvisited_days_threshold',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.INTEGER,
        'label': 'RULE-06: Unvisited Farm Scanner Threshold (Days)',
        'description': 'Days since last extension visit that triggers automatic enlistment into the Visit Priority Queue (default: 60 days).',
        'value': '60',
        'default_value': '60',
    },
    {
        'key': 'fieldops_rule06_baseline_priority_score',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.INTEGER,
        'label': 'RULE-06: Baseline Priority Score',
        'description': 'Initial priority score given to an overdue farm when auto-enlisted by RULE-06 scanner.',
        'value': '50',
        'default_value': '50',
    },
    {
        'key': 'fieldops_max_gps_drift_meters',
        'category': ParameterCategory.FIELDOPS,
        'data_type': ParameterDataType.INTEGER,
        'label': 'Field Check-in Max GPS Drift Proximity (Meters)',
        'description': 'Allowable distance between officer mobile check-in GPS and farm coordinates for verified attendance (default: 150m).',
        'value': '150',
        'default_value': '150',
    },

    # Finance & Credit Risk
    {
        'key': 'finance_safe_coverage_ratio',
        'category': ParameterCategory.FINANCE,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Finance: Safe Operating Coverage Ratio',
        'description': 'Minimum ratio of projected harvest value to outstanding debt considered low risk (default: 2.50x).',
        'value': '2.50',
        'default_value': '2.50',
    },
    {
        'key': 'finance_warning_coverage_ratio',
        'category': ParameterCategory.FINANCE,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Finance: Early-Warning Coverage Ratio (RULE-03)',
        'description': 'Coverage ratio threshold below which a MEDIUM risk warning is raised (default: 1.75x).',
        'value': '1.75',
        'default_value': '1.75',
    },
    {
        'key': 'finance_critical_coverage_ratio',
        'category': ParameterCategory.FINANCE,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Finance: Critical Default Coverage Ratio',
        'description': 'Coverage ratio threshold below which a loan is placed on WATCHLIST and subsequent tranches blocked (default: 1.20x).',
        'value': '1.20',
        'default_value': '1.20',
    },
    {
        'key': 'finance_rule02_arrears_grace_days',
        'category': ParameterCategory.FINANCE,
        'data_type': ParameterDataType.INTEGER,
        'label': 'RULE-02: Loan Arrears Grace Period (Days)',
        'description': 'Days past repayment due date before raising a HIGH risk flag and scheduling an urgent inspection (default: 7 days).',
        'value': '7',
        'default_value': '7',
    },
    {
        'key': 'finance_rule05_certificate_credit_bonus',
        'category': ParameterCategory.FINANCE,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'RULE-05: Certified Farmer Credit Score Bonus',
        'description': 'Bonus points added to smallholder credit score for holding an accredited DFAC certificate (default: 15.00 pts).',
        'value': '15.00',
        'default_value': '15.00',
    },
    {
        'key': 'finance_verified_identity_credit_bonus',
        'category': ParameterCategory.FINANCE,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Finance: Verified Farmer & Farm Location Bonus',
        'description': 'Bonus points added to credit score for verified phone, NIN, and GPS farm polygon (default: 10.00 pts).',
        'value': '10.00',
        'default_value': '10.00',
    },

    # Market Linkage
    {
        'key': 'market_matching_delivery_buffer_days',
        'category': ParameterCategory.MARKET,
        'data_type': ParameterDataType.INTEGER,
        'label': 'Market: Sourcing Window Delivery Buffer (Days)',
        'description': 'Tolerance buffer applied before and after buyer delivery window for match candidates (default: 7 days).',
        'value': '7',
        'default_value': '7',
    },
    {
        'key': 'market_default_max_radius_km',
        'category': ParameterCategory.MARKET,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Market: Default Sourcing Radius (km)',
        'description': 'Default geographical search radius if off-taker does not specify maximum delivery radius (default: 50.00 km).',
        'value': '50.00',
        'default_value': '50.00',
    },

    # Training & Capacity Building
    {
        'key': 'training_min_attendance_pct',
        'category': ParameterCategory.TRAINING,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Training: Minimum Attendance Rate (%)',
        'description': 'Minimum session attendance percentage required to qualify for certificate issuance (default: 80.00%).',
        'value': '80.00',
        'default_value': '80.00',
    },
    {
        'key': 'training_min_assessment_score_pct',
        'category': ParameterCategory.TRAINING,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'Training: Minimum Assessment Score (%)',
        'description': 'Minimum score in post-training competency assessment required to pass (default: 70.00%).',
        'value': '70.00',
        'default_value': '70.00',
    },
    {
        'key': 'training_certificate_validity_months',
        'category': ParameterCategory.TRAINING,
        'data_type': ParameterDataType.INTEGER,
        'label': 'Training: Certificate Validity Duration (Months)',
        'description': 'Period of validity for security-grade training certificates before renewal is required (default: 24 months).',
        'value': '24',
        'default_value': '24',
    },

    # Production & Harvest Monitoring
    {
        'key': 'production_rule01_harvest_ready_days',
        'category': ParameterCategory.PRODUCTION,
        'data_type': ParameterDataType.INTEGER,
        'label': 'RULE-01: Harvest Readiness Forecast Window (Days)',
        'description': 'Days before projected harvest date when batch transitions from FORECASTED to AVAILABLE for market matching.',
        'value': '14',
        'default_value': '14',
    },
    {
        'key': 'production_rule03_yield_deficit_pct',
        'category': ParameterCategory.PRODUCTION,
        'data_type': ParameterDataType.DECIMAL,
        'label': 'RULE-03: Yield Deficit Warning Percentage (%)',
        'description': 'Deficit percentage below breed benchmark weight that triggers an early-warning risk flag (default: 25.00%).',
        'value': '25.00',
        'default_value': '25.00',
    },
]


def seed_system_parameters():
    """Initializes or updates default system parameters in the database."""
    created_count = 0
    for param_data in DEFAULT_PARAMETERS:
        obj, created = SystemParameter.objects.get_or_create(
            key=param_data['key'],
            defaults=param_data
        )
        if created:
            created_count += 1
    return created_count
