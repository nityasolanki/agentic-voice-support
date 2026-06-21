"""
Refund Agent.
Checks eligibility and submits refund requests.
"""
from datetime import datetime, timezone, timedelta

from backend.db.crud import get_orders_by_customer, create_refund
from backend.db.models import OrderStatus
from backend.memory.session import CustomerSession
from backend.services.gmail import send_refund_confirmation

REFUND_WINDOW_DAYS = 30  # Policy: refunds within 30 days of delivery


async def run_refund(
    session: CustomerSession,
    user_message: str,
    db,
) -> str:
    if not session.is_verified or not session.customer_id:
        return "I need to verify your identity first before processing a refund."

    orders = await get_orders_by_customer(db, session.customer_id)
    if not orders:
        return "I don't see any orders on your account that can be refunded."

    # Find the most recent eligible order
    eligible_order = None
    for order in orders:
        if order.status == OrderStatus.DELIVERED and order.delivered_at:
            days_since = (datetime.now(timezone.utc) - order.delivered_at).days
            if days_since <= REFUND_WINDOW_DAYS:
                eligible_order = order
                break

    if not eligible_order:
        return (
            "I checked your recent orders and unfortunately none are currently "
            f"eligible for a refund. Our policy covers refunds within {REFUND_WINDOW_DAYS} days "
            "of delivery. Would you like me to create a support ticket to review your case?"
        )

    # Create the refund
    refund = await create_refund(
        db=db,
        order_id=eligible_order.id,
        amount=eligible_order.total_amount,
        reason=user_message,
    )

    # Send confirmation email
    try:
        await send_refund_confirmation(
            to_email=session.customer_email,
            customer_name=session.customer_name,
            refund_id=refund.id,
            order_id=eligible_order.id,
            amount=refund.amount,
        )
    except Exception:
        pass  # Don't fail the flow if email fails

    return (
        f"I've submitted a refund request for your order {eligible_order.id}. "
        f"Refund ID: {refund.id}. "
        f"The amount of ${refund.amount:.2f} will be returned to your original payment method "
        "within 3–5 business days. I've also sent a confirmation to your email. "
        "Is there anything else I can help you with?"
    )
