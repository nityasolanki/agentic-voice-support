"""Tools for refund eligibility checking and processing."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta
from langchain_core.tools import tool
from sqlalchemy.orm import Session
from sqlalchemy import select

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend.db.models import Order, Refund, RefundStatus, OrderStatus
from backend.db.session import sync_engine

REFUND_WINDOW_DAYS = 30


def _get_session():
    return Session(sync_engine)


@tool
def check_refund_eligibility(order_number: str) -> dict:
    """Check if an order is eligible for a refund based on company policy."""
    with _get_session() as db:
        order = db.scalar(select(Order).where(Order.order_number == order_number))
        if not order:
            return {"eligible": False, "reason": f"Order {order_number} not found."}

        if order.status == OrderStatus.CANCELLED:
            return {"eligible": False, "reason": "Order is already cancelled."}

        if order.status == OrderStatus.RETURNED:
            return {"eligible": False, "reason": "A return has already been processed for this order."}

        days_since_order = (datetime.utcnow() - order.created_at).days
        if days_since_order > REFUND_WINDOW_DAYS:
            return {
                "eligible": False,
                "reason": f"Order is {days_since_order} days old. Refund window is {REFUND_WINDOW_DAYS} days.",
            }

        return {
            "eligible": True,
            "order_number": order_number,
            "order_amount": order.total_amount,
            "days_since_order": days_since_order,
            "refund_window_days": REFUND_WINDOW_DAYS,
            "message": "Order is eligible for a full refund.",
        }


@tool
def process_refund(order_number: str, reason: str, amount: float | None = None) -> dict:
    """Process a refund request for an eligible order."""
    with _get_session() as db:
        order = db.scalar(select(Order).where(Order.order_number == order_number))
        if not order:
            return {"success": False, "error": f"Order {order_number} not found."}

        refund_amount = amount if amount else order.total_amount
        refund_number = f"REF-{uuid.uuid4().hex[:8].upper()}"

        refund = Refund(
            refund_number=refund_number,
            order_id=order.id,
            amount=refund_amount,
            reason=reason,
            status=RefundStatus.PENDING,
        )
        order.status = OrderStatus.RETURNED
        db.add(refund)
        db.commit()
        db.refresh(refund)

        return {
            "success": True,
            "refund_number": refund.refund_number,
            "amount": refund.amount,
            "status": refund.status.value,
            "message": f"Refund of ${refund.amount:.2f} submitted. "
                       "Processing takes 5-7 business days to your original payment method.",
        }
