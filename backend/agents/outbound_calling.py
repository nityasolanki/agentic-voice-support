"""
Outbound Calling Agent.
Proactively calls customers for delay notifications, ticket follow-ups, etc.
"""
from datetime import datetime, timezone, timedelta

from backend.db.crud import get_customer_by_id, get_open_tickets, log_call
from backend.db.models import OrderStatus
from backend.services.twilio_service import (
    make_outbound_call,
    build_delay_notification_message,
    build_ticket_followup_message,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def notify_delayed_orders(db: AsyncSession):
    """
    Scan for delayed orders and call affected customers.
    Intended to be run as a scheduled job.
    """
    from sqlalchemy import select
    from backend.db.models import Order

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Order).where(
            Order.status == OrderStatus.SHIPPED,
            Order.estimated_delivery < now,
        ).limit(20)
    )
    delayed_orders = result.scalars().all()

    call_results = []
    for order in delayed_orders:
        customer = await get_customer_by_id(db, order.customer_id)
        if not customer or not customer.phone:
            continue

        new_eta = (now + timedelta(days=2)).strftime("%B %d")
        message = build_delay_notification_message(
            customer_name=customer.name,
            order_id=order.id,
            new_eta=new_eta,
        )

        try:
            result = await make_outbound_call(
                to_number=customer.phone,
                message=message,
                customer_id=customer.id,
                reason="delay_notification",
            )
            await log_call(
                db=db,
                customer_id=customer.id,
                direction="outbound",
                outcome="initiated",
                twilio_call_sid=result.get("call_sid"),
                notes=f"Delay notification for order {order.id}",
            )
            call_results.append(result)
        except Exception as e:
            call_results.append({"error": str(e), "customer_id": customer.id})

    return call_results


async def follow_up_open_tickets(db: AsyncSession):
    """
    Follow up on tickets that have been open for more than 24 hours.
    """
    tickets = await get_open_tickets(db, limit=20)
    call_results = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    stale = [t for t in tickets if t.created_at and t.created_at < cutoff]

    for ticket in stale:
        customer = await get_customer_by_id(db, ticket.customer_id)
        if not customer or not customer.phone:
            continue

        message = build_ticket_followup_message(
            customer_name=customer.name,
            ticket_id=ticket.id,
        )

        try:
            result = await make_outbound_call(
                to_number=customer.phone,
                message=message,
                customer_id=customer.id,
                reason="ticket_followup",
            )
            await log_call(
                db=db,
                customer_id=customer.id,
                direction="outbound",
                outcome="initiated",
                twilio_call_sid=result.get("call_sid"),
                notes=f"Follow-up for ticket {ticket.id}",
            )
            call_results.append(result)
        except Exception as e:
            call_results.append({"error": str(e), "ticket_id": ticket.id})

    return call_results
