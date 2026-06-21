"""
Outbound Calling Agent — proactively contacts customers for:
- Delayed shipment notifications
- Ticket follow-ups
- Subscription renewal reminders
- Satisfaction surveys

Run as a background scheduler (APScheduler / cron).
"""
from __future__ import annotations
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import select

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend.db.models import Order, OrderStatus, SupportTicket, TicketStatus, Customer
from backend.db.session import sync_engine
from backend.tools.twilio_tools import initiate_outbound_call
from backend.tools.email_tools import send_order_update


def find_delayed_shipments() -> list[dict]:
    """Find orders that are past estimated delivery and not yet delivered."""
    with Session(sync_engine) as db:
        now = datetime.utcnow()
        delayed = db.scalars(
            select(Order).where(
                Order.status == OrderStatus.SHIPPED,
                Order.estimated_delivery < now,
            )
        ).all()
        results = []
        for order in delayed:
            customer = db.get(Customer, order.customer_id)
            if customer and customer.phone:
                results.append({
                    "order_number": order.order_number,
                    "customer_id": customer.id,
                    "customer_name": customer.name,
                    "customer_phone": customer.phone,
                    "customer_email": customer.email,
                    "estimated_delivery": order.estimated_delivery,
                })
        return results


def find_stale_tickets(inactivity_days: int = 3) -> list[dict]:
    """Find open tickets with no activity for N days."""
    cutoff = datetime.utcnow() - timedelta(days=inactivity_days)
    with Session(sync_engine) as db:
        tickets = db.scalars(
            select(SupportTicket).where(
                SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]),
                SupportTicket.updated_at < cutoff,
            )
        ).all()
        results = []
        for ticket in tickets:
            customer = db.get(Customer, ticket.customer_id)
            if customer and customer.phone:
                results.append({
                    "ticket_number": ticket.ticket_number,
                    "subject": ticket.subject,
                    "customer_name": customer.name,
                    "customer_phone": customer.phone,
                    "customer_email": customer.email,
                })
        return results


def run_delay_notification_campaign():
    """Outbound: notify customers with delayed shipments."""
    delayed = find_delayed_shipments()
    print(f"[Outbound] Found {len(delayed)} delayed shipments.")
    for item in delayed[:10]:  # Cap at 10 per run to avoid flooding
        message = (
            f"Hello {item['customer_name']}, this is your AI support assistant calling about "
            f"order {item['order_number']}. Your shipment is running behind schedule. "
            f"We sincerely apologize for the delay. Please call us back or reply to our email for assistance."
        )
        result = initiate_outbound_call.invoke({
            "customer_phone": item["customer_phone"],
            "message": message,
            "customer_id": item["customer_id"],
        })
        print(f"[Outbound] Called {item['customer_name']}: {result}")


def run_ticket_followup_campaign():
    """Outbound: follow up on stale support tickets."""
    stale = find_stale_tickets()
    print(f"[Outbound] Found {len(stale)} stale tickets.")
    for item in stale[:10]:
        message = (
            f"Hello {item['customer_name']}, this is an AI support assistant following up on "
            f"your support ticket {item['ticket_number']} regarding {item['subject']}. "
            f"Please call us back or log into your account to update the ticket."
        )
        result = initiate_outbound_call.invoke({
            "customer_phone": item["customer_phone"],
            "message": message,
            "customer_id": 0,
        })
        print(f"[Outbound] Followed up with {item['customer_name']}: {result}")


if __name__ == "__main__":
    print("Running outbound campaigns...")
    run_delay_notification_campaign()
    run_ticket_followup_campaign()
    print("Done.")
