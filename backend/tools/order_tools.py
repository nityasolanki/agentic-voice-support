"""Tools for order retrieval and shipment status."""
from __future__ import annotations
from langchain_core.tools import tool
from sqlalchemy.orm import Session
from sqlalchemy import select

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend.db.models import Order, Customer, OrderItem, Product
from backend.db.session import sync_engine


def _get_session():
    return Session(sync_engine)


@tool
def get_order_by_number(order_number: str) -> dict:
    """Retrieve order details by order number like ORD-001."""
    with _get_session() as db:
        # Try exact match first, then with ORD- prefix
        order = db.scalar(select(Order).where(Order.order_number == order_number))
        if not order and not order_number.startswith("ORD-"):
            order = db.scalar(select(Order).where(
                Order.order_number == f"ORD-{order_number}"
            ))
        if not order:
            return {"error": f"Order {order_number} not found."}
        items = []
        for item in order.items:
            items.append({
                "product": item.product.name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
            })
        return {
            "order_number": order.order_number,
            "status": order.status.value,
            "total_amount": order.total_amount,
            "carrier": order.carrier,
            "tracking_number": order.tracking_number,
            "estimated_delivery": str(order.estimated_delivery) if order.estimated_delivery else None,
            "shipped_at": str(order.shipped_at) if order.shipped_at else None,
            "delivered_at": str(order.delivered_at) if order.delivered_at else None,
            "items": items,
        }


@tool
def get_orders_for_customer(customer_id: int, limit: int = 5) -> list[dict]:
    """Get recent orders for a customer. customer_id must be an integer."""
    try:
        customer_id = int(customer_id)
    except (ValueError, TypeError):
        return [{"error": f"Invalid customer_id: {customer_id}"}]

    with _get_session() as db:
        orders = db.scalars(
            select(Order)
            .where(Order.customer_id == customer_id)
            .order_by(Order.created_at.desc())
            .limit(limit)
        ).all()
        if not orders:
            return [{"error": f"No orders found for customer {customer_id}"}]
        return [
            {
                "order_number": o.order_number,
                "status": o.status.value,
                "total_amount": o.total_amount,
                "created_at": str(o.created_at),
                "estimated_delivery": str(o.estimated_delivery) if o.estimated_delivery else None,
            }
            for o in orders
        ]


@tool
def get_shipment_status(tracking_number: str) -> dict:
    """Get shipment status by tracking number."""
    with _get_session() as db:
        order = db.scalar(
            select(Order).where(Order.tracking_number == tracking_number)
        )
        if not order:
            return {"error": f"No order found with tracking number {tracking_number}"}
        return {
            "tracking_number": tracking_number,
            "carrier": order.carrier,
            "status": order.status.value,
            "estimated_delivery": str(order.estimated_delivery) if order.estimated_delivery else None,
            "shipped_at": str(order.shipped_at) if order.shipped_at else None,
        }