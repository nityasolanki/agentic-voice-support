"""Tools for support ticket creation and management."""
from __future__ import annotations
import uuid
from datetime import datetime
from langchain_core.tools import tool
from sqlalchemy.orm import Session
from sqlalchemy import select

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend.db.models import SupportTicket, Order, TicketStatus, TicketPriority
from backend.db.session import sync_engine


def _get_session():
    return Session(sync_engine)


def _resolve_order_id(order_id_or_number) -> int | None:
    """Accept either an integer order ID or a string order number like ORD-001."""
    if order_id_or_number is None:
        return None
    # Already an integer
    if isinstance(order_id_or_number, int):
        return order_id_or_number
    # String — try parsing as int first
    try:
        return int(order_id_or_number)
    except (ValueError, TypeError):
        pass
    # String order number like "ORD-001" — look up the real ID
    with _get_session() as db:
        order = db.scalar(select(Order).where(Order.order_number == str(order_id_or_number).strip()))
        return order.id if order else None


@tool
def create_support_ticket(
    customer_id: int,
    subject: str,
    description: str,
    category: str,
    priority: str = "medium",
    order_id: str | int | None = None,
) -> dict:
    """Create a new support ticket. order_id can be an integer ID or string like ORD-001."""
    try:
        prio = TicketPriority(priority.lower())
    except ValueError:
        prio = TicketPriority.MEDIUM

    # Resolve order_id — handles both integer IDs and string order numbers
    resolved_order_id = _resolve_order_id(order_id)

    with _get_session() as db:
        ticket_number = f"TKT-{uuid.uuid4().hex[:8].upper()}"
        ticket = SupportTicket(
            ticket_number=ticket_number,
            customer_id=customer_id,
            order_id=resolved_order_id,
            status=TicketStatus.OPEN,
            priority=prio,
            category=category,
            subject=subject,
            description=description,
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return {
            "ticket_number": ticket.ticket_number,
            "status": ticket.status.value,
            "priority": ticket.priority.value,
            "category": ticket.category,
            "subject": ticket.subject,
            "created_at": str(ticket.created_at),
        }


@tool
def get_ticket_status(ticket_number: str) -> dict:
    """Get the current status of a support ticket."""
    with _get_session() as db:
        ticket = db.scalar(select(SupportTicket).where(SupportTicket.ticket_number == ticket_number))
        if not ticket:
            return {"error": f"Ticket {ticket_number} not found."}
        return {
            "ticket_number": ticket.ticket_number,
            "status": ticket.status.value,
            "priority": ticket.priority.value,
            "subject": ticket.subject,
            "category": ticket.category,
            "created_at": str(ticket.created_at),
            "resolution": ticket.resolution,
        }


@tool
def escalate_ticket(ticket_number: str, reason: str) -> dict:
    """Escalate a support ticket to human agents."""
    with _get_session() as db:
        ticket = db.scalar(select(SupportTicket).where(SupportTicket.ticket_number == ticket_number))
        if not ticket:
            return {"error": f"Ticket {ticket_number} not found."}
        ticket.status = TicketStatus.ESCALATED
        ticket.priority = TicketPriority.HIGH
        ticket.description += f"\n\n[ESCALATED]: {reason}"
        db.commit()
        return {
            "success": True,
            "ticket_number": ticket_number,
            "message": f"Ticket {ticket_number} escalated to a human support agent.",
        }