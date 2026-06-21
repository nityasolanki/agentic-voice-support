"""
Order Management Agent.
Retrieves and explains order/shipment status.
"""
from backend.db.crud import get_orders_by_customer, get_order_by_id
from backend.memory.session import CustomerSession
from backend.db.models import OrderStatus


STATUS_MESSAGES = {
    OrderStatus.PENDING: "is being processed and will ship soon",
    OrderStatus.PROCESSING: "is currently being prepared for shipment",
    OrderStatus.SHIPPED: "has been shipped",
    OrderStatus.OUT_FOR_DELIVERY: "is out for delivery and should arrive today",
    OrderStatus.DELIVERED: "has been delivered",
    OrderStatus.CANCELLED: "has been cancelled",
    OrderStatus.RETURNED: "has been returned",
}


async def run_order_management(
    session: CustomerSession,
    user_message: str,
    db,
) -> str:
    """
    Retrieve and explain order status for the verified customer.
    """
    if not session.is_verified or not session.customer_id:
        return "I need to verify your identity first. What email is your account under?"

    orders = await get_orders_by_customer(db, session.customer_id)

    if not orders:
        return (
            "I don't see any orders associated with your account. "
            "If you believe this is an error, I can create a support ticket for you."
        )

    # Focus on the most recent order
    order = orders[0]
    session.current_order_id = order.id

    status_desc = STATUS_MESSAGES.get(order.status, "has an unknown status")
    response_parts = [
        f"Your most recent order ({order.id}) {status_desc}."
    ]

    if order.tracking_number:
        response_parts.append(
            f"Tracking number: {order.tracking_number} via {order.carrier or 'the carrier'}."
        )

    if order.estimated_delivery and order.status not in (OrderStatus.DELIVERED, OrderStatus.CANCELLED):
        eta = order.estimated_delivery.strftime("%B %d")
        response_parts.append(f"Estimated delivery: {eta}.")

    # Delayed order → offer ticket
    if order.status == OrderStatus.SHIPPED and order.estimated_delivery:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if order.estimated_delivery < now:
            response_parts.append(
                "It looks like this order is running late. "
                "Would you like me to create a priority support ticket?"
            )

    response_parts.append("Is there anything else I can help you with?")
    return " ".join(response_parts)
