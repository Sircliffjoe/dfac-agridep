import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from agridep.apps.registry.models import Farmer, Farm
from agridep.apps.finance.models import LoanRecord, LoanTranche, TrancheStatus
from agridep.apps.inputs.models import (
    InputSupplier,
    InputCatalogItem,
    InputOrder,
    InputOrderItem,
    OrderStatus,
    DeliveryConfirmationChannel,
)
from agridep.apps.audit.services import log_audit_event

logger = logging.getLogger('agridep.inputs')


@transaction.atomic
def create_input_order(
    farmer: Farmer,
    farm: Farm,
    supplier: InputSupplier,
    items: List[Dict[str, Any]],
    loan: Optional[LoanRecord] = None,
    tranche: Optional[LoanTranche] = None,
    created_by=None
) -> InputOrder:
    """
    Creates an InputOrder for in-kind agricultural inputs, linking to a loan tranche if applicable.
    items is a list of dicts: [{'catalog_item': item, 'quantity': Decimal('10')}, ...]
    """
    if not items:
        raise ValidationError("Input order must contain at least one item.")

    order = InputOrder.objects.create(
        farmer=farmer,
        farm=farm,
        supplier=supplier,
        loan=loan,
        tranche=tranche,
        status=OrderStatus.SUBMITTED,
        total_amount_naira=Decimal('0.00'),
    )

    total_amount = Decimal('0.00')
    for entry in items:
        catalog_item: InputCatalogItem = entry['catalog_item']
        quantity = Decimal(str(entry['quantity']))
        unit_price = catalog_item.unit_price_naira
        line_total = quantity * unit_price

        InputOrderItem.objects.create(
            order=order,
            catalog_item=catalog_item,
            quantity=quantity,
            unit_price_naira=unit_price,
            total_price_naira=line_total,
        )
        total_amount += line_total

    order.total_amount_naira = total_amount
    order.save(update_fields=['total_amount_naira'])

    # Link order reference to loan tranche if provided
    if tranche:
        tranche.input_order_reference = order.order_code
        tranche.save(update_fields=['input_order_reference', 'updated_at'])

    log_audit_event(
        action='CREATE_INPUT_ORDER',
        resource_type='InputOrder',
        resource_id=str(order.id),
        user=created_by,
        details={
            'order_code': order.order_code,
            'supplier': supplier.supplier_name,
            'farmer': f"{farmer.first_name} {farmer.last_name}",
            'total_amount_naira': float(total_amount),
            'tranche_id': str(tranche.id) if tranche else None,
        }
    )

    logger.info(f"InputOrder {order.order_code} created: ₦{total_amount:,.2f} for {farmer.phone_normalized}")
    return order


@transaction.atomic
def dispatch_input_order(
    order: InputOrder,
    waybill_number: str = '',
    dispatched_by=None
) -> InputOrder:
    """Marks an input order as dispatched from the supplier depot."""
    if order.status not in [OrderStatus.SUBMITTED, OrderStatus.SUPPLIER_ACCEPTED]:
        raise ValidationError(f"Cannot dispatch order in state '{order.get_status_display()}'.")

    order.status = OrderStatus.DISPATCHED
    order.dispatched_at = timezone.now()
    order.waybill_number = waybill_number
    order.save(update_fields=['status', 'dispatched_at', 'waybill_number', 'updated_at'])

    log_audit_event(
        action='DISPATCH_INPUT_ORDER',
        resource_type='InputOrder',
        resource_id=str(order.id),
        user=dispatched_by,
        details={'order_code': order.order_code, 'waybill': waybill_number}
    )
    return order


@transaction.atomic
def confirm_input_delivery(
    order: InputOrder,
    confirmation_channel: str = DeliveryConfirmationChannel.FIELD_OFFICER_INSPECTION,
    confirmed_by=None,
    notes: str = ''
) -> InputOrder:
    """
    Confirms physical receipt of in-kind inputs on-farm (Rule-08 milestone verification).
    Unblocks linked loan tranche for subsequent disbursement.
    """
    order.status = OrderStatus.DELIVERED_CONFIRMED
    order.delivered_at = timezone.now()
    order.delivery_confirmation_channel = confirmation_channel
    order.delivery_confirmed_by = confirmed_by
    order.delivery_notes = notes
    order.save(update_fields=[
        'status', 'delivered_at', 'delivery_confirmation_channel',
        'delivery_confirmed_by', 'delivery_notes', 'updated_at'
    ])

    # If linked to a tranche, mark the tranche as ready or fulfilled
    if order.tranche:
        tranche = order.tranche
        if tranche.status == TrancheStatus.PENDING_APPROVAL or tranche.status == TrancheStatus.BLOCKED:
            tranche.status = TrancheStatus.APPROVED
            tranche.save(update_fields=['status', 'updated_at'])

    log_audit_event(
        action='CONFIRM_INPUT_DELIVERY',
        resource_type='InputOrder',
        resource_id=str(order.id),
        user=confirmed_by,
        details={
            'order_code': order.order_code,
            'channel': confirmation_channel,
            'notes': notes
        }
    )
    logger.info(f"InputOrder {order.order_code} delivery CONFIRMED via {confirmation_channel}")
    return order


def verify_tranche_input_delivery_gate(tranche: LoanTranche) -> Dict[str, Any]:
    """
    Enforces Rule-08: Staged Input Order & Milestone Delivery Gate.
    Returns whether this tranche is unblocked to proceed with disbursement.
    """
    loan = tranche.loan

    # If this is tranche 1, check if it's already in order
    if tranche.tranche_number == 1:
        return {"allowed": True, "reason": "First tranche has no prior delivery dependency."}

    # For tranche N > 1, check all prior tranches
    prior_tranches = loan.tranches.filter(tranche_number__lt=tranche.tranche_number).order_by('tranche_number')
    for pt in prior_tranches:
        # Check if previous tranche had in-kind input orders
        linked_orders = InputOrder.objects.filter(tranche=pt)
        if linked_orders.exists():
            unconfirmed = linked_orders.exclude(status=OrderStatus.DELIVERED_CONFIRMED)
            if unconfirmed.exists():
                unconfirmed_codes = list(unconfirmed.values_list('order_code', flat=True))
                return {
                    "allowed": False,
                    "reason": f"Tranche #{pt.tranche_number} has unconfirmed input orders: {', '.join(unconfirmed_codes)}",
                    "blocked_by_orders": unconfirmed_codes,
                    "blocked_by_tranche": pt.tranche_number
                }
        elif pt.status != TrancheStatus.DISBURSED:
            return {
                "allowed": False,
                "reason": f"Prior Tranche #{pt.tranche_number} is not disbursed (Status: {pt.get_status_display()}).",
                "blocked_by_tranche": pt.tranche_number
            }

    return {"allowed": True, "reason": "All prior tranches and input orders are verified and fulfilled."}
