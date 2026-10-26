import logging
from decimal import Decimal
from typing import Optional, List
from django.utils import timezone
from agridep.apps.alerts.models import (
    AlertNotification,
    AlertRule,
    AlertChannel,
    AlertPriority,
    AlertStatus,
)
from agridep.apps.alerts.adapters import get_sms_adapter

logger = logging.getLogger(__name__)


def send_transactional_sms(
    phone_number: str,
    message: str,
    priority: str = AlertPriority.NORMAL,
    rule: Optional[AlertRule] = None,
    user=None
) -> AlertNotification:
    """
    Core transactional SMS dispatch engine.
    Dispatches via Africa's Talking adapter and records an immutable AlertNotification audit trail.
    """
    notification = AlertNotification.objects.create(
        rule=rule,
        recipient_phone=phone_number,
        recipient_user=user,
        channel=AlertChannel.SMS,
        priority=priority,
        message_text=message,
        status=AlertStatus.QUEUED
    )

    adapter = get_sms_adapter()
    result = adapter.send_sms(phone_number, message)

    notification.sent_at = timezone.now()
    notification.provider_response = result

    if result.get('status') == 'SUCCESS':
        notification.status = AlertStatus.SENT
        recipients = result.get('data', {}).get('SMSMessageData', {}).get('Recipients', [])
        if recipients:
            notification.provider_reference = recipients[0].get('messageId', '')
    else:
        notification.status = AlertStatus.FAILED

    notification.save(update_fields=['status', 'sent_at', 'provider_reference', 'provider_response', 'updated_at'])
    return notification


def notify_harvest_readiness(produce_batch) -> Optional[AlertNotification]:
    """
    RULE-01: Dispatches SMS notification when a produce batch enters the 14-day pre-harvest window.
    """
    farmer = produce_batch.farm.farmer
    phone = farmer.phone_normalized
    if not phone:
        return None

    days = 14
    if produce_batch.projected_harvest_window_start:
        days = max(1, (produce_batch.projected_harvest_window_start - timezone.localdate()).days)

    message = (
        f"DFAC AgriDEP Alert: Hello {farmer.first_name}, your {produce_batch.produce_type.name} batch on "
        f"{produce_batch.farm.name} is harvest-ready in ~{days} days. Commercial off-takers are actively matching. "
        "Dial *384*223# to review offers."
    )
    return send_transactional_sms(phone, message, priority=AlertPriority.HIGH, user=farmer.user)


def notify_repayment_due(loan_record, days_overdue: int = 7) -> Optional[AlertNotification]:
    """
    RULE-02: Dispatches loan arrears reminder SMS.
    """
    farmer = loan_record.farmer
    phone = farmer.phone_normalized
    if not phone:
        return None

    balance = loan_record.principal_amount_naira - loan_record.total_repaid_naira
    message = (
        f"DFAC AgriDEP Notice: Loan {loan_record.reference_code} has an overdue balance of "
        f"NGN {balance:,.0f} ({days_overdue} days past due). Please make payment to maintain your credit score. "
        "Dial *384*223# for repayment details."
    )
    return send_transactional_sms(phone, message, priority=AlertPriority.HIGH, user=farmer.user)


def notify_emergency_disease(farm, incident_report) -> List[AlertNotification]:
    """
    Broadcasts biosecurity alert to farmers within the same LGA / community upon CRITICAL disease outbreak.
    """
    from agridep.apps.registry.models import Farmer

    # Notify affected farmer first
    affected_phone = farm.farmer.phone_normalized
    notifications = []
    if affected_phone:
        msg = (
            f"DFAC BIOSECURITY ALERT: Emergency {incident_report.get_incident_type_display()} recorded for "
            f"{farm.name}. An urgent extension officer visit has been dispatched. Suspend water discharge."
        )
        n = send_transactional_sms(affected_phone, msg, priority=AlertPriority.EMERGENCY, user=farm.farmer.user)
        notifications.append(n)

    # Broadcast to neighboring cluster farmers in same LGA
    neighbors = Farmer.objects.filter(lga=farm.farmer.lga).exclude(id=farm.farmer.id)[:10]
    for n_farmer in neighbors:
        if n_farmer.phone_normalized:
            b_msg = (
                f"DFAC ADVISORY: Notice of suspected fish disease reported in {farm.farmer.lga}. "
                "Disinfect sampling nets and monitor morning dissolved oxygen levels. Dial *384*223# to report."
            )
            notif = send_transactional_sms(n_farmer.phone_normalized, b_msg, priority=AlertPriority.HIGH, user=n_farmer.user)
            notifications.append(notif)

    return notifications


def notify_buyer_match_proposed(match) -> Optional[AlertNotification]:
    """
    RULE-04: Notifies farmer when an off-taker demand has matched their produce batch.
    """
    farmer = match.produce_batch.farm.farmer
    phone = farmer.phone_normalized
    if not phone:
        return None

    buyer_name = match.buyer_demand.buyer.company_name
    price = match.agreed_price_per_kg_naira or match.buyer_demand.offered_price_per_kg_naira

    message = (
        f"DFAC Produce Match: {buyer_name} has matched your batch for {match.allocated_volume_kg:,.0f}kg "
        f"@ NGN {price:,.0f}/kg. Dial *384*223# (Option 4) to accept or decline."
    )
    return send_transactional_sms(phone, message, priority=AlertPriority.NORMAL, user=farmer.user)
