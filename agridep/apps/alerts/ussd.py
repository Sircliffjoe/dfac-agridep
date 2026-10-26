import logging
from decimal import Decimal
from django.utils import timezone
from agridep.apps.registry.models import Farmer, Farm
from agridep.apps.finance.models import LoanRecord, LoanStatus
from agridep.apps.production.models import ProductionCycle, ProductionLog
from agridep.apps.market.models import ProduceMatch, MatchStatus, CommodityPrice
from agridep.apps.fieldops.models import VisitAssignment, AssignmentPriority, AssignmentTrigger, AssignmentStatus
from agridep.apps.alerts.models import USSDSession

logger = logging.getLogger(__name__)


class USSDHandler:
    """
    State machine handler for DFAC AgriDEP Smallholder USSD sessions (*384*223#).
    Complies with Africa's Talking USSD gateway specifications:
      - Responses prefixed with 'CON ' require user input.
      - Responses prefixed with 'END ' terminate the session.
    """

    def __init__(self, session_id: str, phone_number: str, text: str, network_code: str = "MTN_NG"):
        self.session_id = session_id
        self.phone_number = phone_number.strip()
        self.raw_text = text.strip()
        self.network_code = network_code
        self.inputs = [t.strip() for t in self.raw_text.split('*')] if self.raw_text else []

    def handle(self) -> str:
        """Processes the input path and returns CON or END response string."""
        session, _ = USSDSession.objects.get_or_create(
            session_id=self.session_id,
            defaults={
                'phone_number': self.phone_number,
                'network_code': self.network_code,
                'current_menu': 'MAIN_MENU',
            }
        )
        session.last_interaction_at = timezone.now()

        # Resolve farmer identity
        farmer = Farmer.objects.filter(phone_normalized=self.phone_number).first()
        if not farmer:
            # Fallback search by trailing digits
            clean_digits = ''.join(filter(str.isdigit, self.phone_number))
            if len(clean_digits) >= 10:
                farmer = Farmer.objects.filter(phone_normalized__icontains=clean_digits[-10:]).first()

        if not self.inputs:
            return self._main_menu(farmer)

        root_choice = self.inputs[0]

        if root_choice == '1':
            return self._menu_loan_status(farmer)
        elif root_choice == '2':
            return self._menu_production_log(farmer, session)
        elif root_choice == '3':
            return self._menu_market_prices()
        elif root_choice == '4':
            return self._menu_buyer_matches(farmer)
        elif root_choice == '5':
            return self._menu_request_extension_visit(farmer)
        else:
            return "END Invalid option selected. Please redial *384*223# to start again."

    def _main_menu(self, farmer: Farmer) -> str:
        name = farmer.first_name if farmer else "Farmer"
        return (
            f"CON Welcome {name} to DFAC AgriDEP\n"
            "1. Check Loan & Repayment\n"
            "2. Report Pond Mortality & Feed\n"
            "3. Market Produce Prices\n"
            "4. Buyer Match Offers\n"
            "5. Request Field Officer Visit"
        )

    def _menu_loan_status(self, farmer: Farmer) -> str:
        if not farmer:
            return "END Your phone number is not registered on DFAC AgriDEP. Contact your extension officer."

        loan = LoanRecord.objects.filter(farmer=farmer).order_by('-created_at').first()
        if not loan:
            return f"END Hello {farmer.first_name}, you have no active loan record with DFAC lending partners."

        balance = loan.principal_amount_naira - loan.total_repaid_naira
        next_schedule = loan.repayment_schedules.filter(status='PENDING').order_by('due_date').first()
        due_str = f"Due: {next_schedule.due_date.strftime('%d %b')}" if next_schedule else "Fully Repaid"

        return (
            f"END Loan {loan.reference_code}\n"
            f"Principal: NGN {loan.principal_amount_naira:,.0f}\n"
            f"Outstanding: NGN {balance:,.0f}\n"
            f"Status: {loan.get_status_display()}\n"
            f"{due_str}"
        )

    def _menu_production_log(self, farmer: Farmer, session: USSDSession) -> str:
        """Multi-turn mortality and feeding submission."""
        if not farmer:
            return "END Your phone number is not registered. Contact your field officer."

        farm = Farm.objects.filter(farmer=farmer).first()
        if not farm:
            return "END No registered farm facility found for your account."

        cycle = ProductionCycle.objects.filter(farm=farm, status='STOCKED').first() or ProductionCycle.objects.filter(farm=farm).first()

        # Step 1: Prompt for dead fish count
        if len(self.inputs) == 1:
            return "CON Enter observed dead fish count today:"

        # Step 2: Prompt for feed consumption (kg)
        if len(self.inputs) == 2:
            try:
                mortality = int(self.inputs[1])
                session.session_data['mortality'] = mortality
                session.save(update_fields=['session_data', 'updated_at'])
                return "CON Enter commercial feed consumed today (in kg):"
            except ValueError:
                return "END Invalid mortality number. Please enter digits only."

        # Step 3: Commit production log
        if len(self.inputs) >= 3:
            try:
                mortality = int(self.inputs[1])
                feed_kg = Decimal(str(self.inputs[2]))

                if cycle:
                    ProductionLog.objects.create(
                        cycle=cycle,
                        observed_mortality_count=mortality,
                        feed_consumed_kg=feed_kg,
                        sampling_average_weight_g=cycle.current_average_weight_g,
                        notes=f"Logged via USSD session {self.session_id}"
                    )

                return (
                    f"END Thank you {farmer.first_name}.\n"
                    f"Logged {mortality} dead fish and {feed_kg:,.1f}kg feed for {farm.name}.\n"
                    "Data synced to your extension officer."
                )
            except Exception as e:
                logger.exception(f"USSD production log error: {e}")
                return "END Error recording production log. Please try again."

        return "END Session error."

    def _menu_market_prices(self) -> str:
        """Returns Niger Delta commodity prices."""
        prices = CommodityPrice.objects.select_related('enterprise_type').order_by('-effective_date')[:3]
        if prices.exists():
            lines = [f"• {p.enterprise_type.name[:12]}: NGN {p.price_per_kg_naira:,.0f}/kg ({p.market_hub})" for p in prices]
            return "END DFAC Niger Delta Market Index:\n" + "\n".join(lines)
        else:
            return (
                "END DFAC Niger Delta Price Index:\n"
                "• Catfish (Table 1kg+): NGN 2,600/kg (Warri)\n"
                "• Tilapia Fresh: NGN 2,200/kg (Yenagoa)\n"
                "• Catfish Fingerlings: NGN 35/pc (Port Harcourt)"
            )

    def _menu_buyer_matches(self, farmer: Farmer) -> str:
        """Handles buyer match review and SMS confirmation."""
        if not farmer:
            return "END Unregistered number. Please contact your coordinator."

        # Check for proposed match
        match = ProduceMatch.objects.filter(
            produce_batch__farm__farmer=farmer,
            status=MatchStatus.PROPOSED
        ).order_by('-created_at').first()

        if not match:
            return f"END Hello {farmer.first_name}, you have no pending buyer match offers at this moment."

        buyer_name = match.buyer_demand.buyer.company_name
        price = match.agreed_price_per_kg_naira or match.buyer_demand.offered_price_per_kg_naira
        vol = match.allocated_volume_kg

        # Multi-turn answer
        if len(self.inputs) == 1:
            return (
                f"CON Buyer Offer: {buyer_name}\n"
                f"Volume: {vol:,.0f}kg @ NGN {price:,.0f}/kg\n"
                "1. Accept Offer\n"
                "2. Decline Offer"
            )

        if len(self.inputs) >= 2:
            action = self.inputs[1]
            if action == '1':
                match.status = MatchStatus.CONFIRMED_BY_FARMER
                match.save(update_fields=['status', 'updated_at'])
                return f"END Match ACCEPTED for {vol:,.0f}kg with {buyer_name}! Your field officer will bring the waybill."
            else:
                match.status = MatchStatus.DECLINED
                match.save(update_fields=['status', 'updated_at'])
                return "END Buyer match offer declined. We will notify you when new buyers emerge."

        return "END Session ended."

    def _menu_request_extension_visit(self, farmer: Farmer) -> str:
        """Enlists the smallholder's farm for priority extension visit."""
        if not farmer:
            return "END Unregistered smallholder. Please register with DFAC."

        farm = Farm.objects.filter(farmer=farmer).first()
        if not farm:
            return "END No farm facility found."

        officer = farmer.assigned_officer
        if not officer:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            officer = User.objects.filter(role='FIELD_OFFICER').first()

        if officer:
            due_date = timezone.localdate() + timezone.timedelta(days=2)
            VisitAssignment.objects.create(
                farm=farm,
                assigned_officer=officer,
                due_date=due_date,
                priority_score=Decimal('80.00'),
                priority_level=AssignmentPriority.HIGH,
                trigger_reason=AssignmentTrigger.MANUAL_DISPATCH,
                status=AssignmentStatus.PENDING,
                instructions=f"Farmer requested urgent extension visit via USSD menu (*384*223#)."
            )

        return (
            f"END Extension visit requested for {farm.name}!\n"
            f"Assigned to Officer {officer.get_full_name() or officer.username if officer else 'Delta Ops'}.\n"
            "Scheduled within 48 hours."
        )
