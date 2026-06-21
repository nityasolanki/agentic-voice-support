"""
CRUD operations for all models.
"""
import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.models import (
    Customer, Order, SupportTicket, Refund, CallLog,
    TicketPriority, TicketStatus, RefundStatus
)


# ── Customer ───────────────────────────────────────────────────────────────

async def get_customer_by_email(db: AsyncSession, email: str) -> Optional[Customer]:
    result = await db.execute(
        select(Customer)
        .where(Customer.email == email)
        .options(selectinload(Customer.orders))
    )
    return result.scalar_one_or_none()


async def get_customer_by_id(db: AsyncSession, customer_id: str) -> Optional[Customer]:
    result = await db.execute(
        select(Customer)
        .where(Customer.id == customer_id)
        .options(selectinload(Customer.orders), selectinload(Customer.tickets))
    )
    return result.scalar_one_or_none()


# ── Orders ─────────────────────────────────────────────────────────────────

async def get_orders_by_customer(db: AsyncSession, customer_id: str) -> List[Order]:
    result = await db.execute(
        select(Order)
        .where(Order.customer_id == customer_id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    return result.scalars().all()


async def get_order_by_id(db: AsyncSession, order_id: str) -> Optional[Order]:
    result = await db.execute(
        select(Order)
        .where(Order.id == order_id)
        .options(selectinload(Order.items), selectinload(Order.customer))
    )
    return result.scalar_one_or_none()


# ── Tickets ────────────────────────────────────────────────────────────────

async def create_ticket(
    db: AsyncSession,
    customer_id: str,
    title: str,
    description: str,
    priority: TicketPriority = TicketPriority.MEDIUM,
    category: str = "general",
    order_id: Optional[str] = None,
) -> SupportTicket:
    ticket = SupportTicket(
        id=f"TKT-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer_id,
        order_id=order_id,
        title=title,
        description=description,
        priority=priority,
        category=category,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


async def update_ticket_status(
    db: AsyncSession,
    ticket_id: str,
    status: TicketStatus,
    resolution_notes: Optional[str] = None,
) -> Optional[SupportTicket]:
    result = await db.execute(select(SupportTicket).where(SupportTicket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket:
        ticket.status = status
        if resolution_notes:
            ticket.resolution_notes = resolution_notes
        if status == TicketStatus.RESOLVED:
            ticket.resolved_at = datetime.utcnow()
        await db.commit()
        await db.refresh(ticket)
    return ticket


async def get_open_tickets(db: AsyncSession, limit: int = 50) -> List[SupportTicket]:
    result = await db.execute(
        select(SupportTicket)
        .where(SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]))
        .order_by(SupportTicket.created_at.asc())
        .limit(limit)
    )
    return result.scalars().all()


# ── Refunds ────────────────────────────────────────────────────────────────

async def create_refund(
    db: AsyncSession,
    order_id: str,
    amount: float,
    reason: str,
) -> Refund:
    refund = Refund(
        id=f"RFD-{uuid.uuid4().hex[:8].upper()}",
        order_id=order_id,
        amount=amount,
        reason=reason,
        status=RefundStatus.PENDING,
    )
    db.add(refund)
    await db.commit()
    await db.refresh(refund)
    return refund


# ── Call Logs ──────────────────────────────────────────────────────────────

async def log_call(
    db: AsyncSession,
    customer_id: str,
    direction: str,
    outcome: str,
    twilio_call_sid: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    notes: Optional[str] = None,
) -> CallLog:
    log = CallLog(
        id=str(uuid.uuid4()),
        customer_id=customer_id,
        twilio_call_sid=twilio_call_sid,
        direction=direction,
        outcome=outcome,
        duration_seconds=duration_seconds,
        notes=notes,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log
