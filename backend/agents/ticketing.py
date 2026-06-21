"""
Ticketing Agent.
Creates and categorizes support tickets.
"""
from backend.db.crud import create_ticket
from backend.db.models import TicketPriority
from backend.memory.session import CustomerSession
from backend.services.gmail import send_ticket_confirmation


CATEGORY_PRIORITY_MAP = {
    "damaged": TicketPriority.HIGH,
    "missing": TicketPriority.HIGH,
    "wrong_item": TicketPriority.MEDIUM,
    "delayed": TicketPriority.MEDIUM,
    "billing": TicketPriority.HIGH,
    "general": TicketPriority.LOW,
}


def infer_category(message: str) -> tuple[str, TicketPriority]:
    msg = message.lower()
    if any(w in msg for w in ["damaged", "broken", "cracked"]):
        return "damaged", TicketPriority.HIGH
    if any(w in msg for w in ["missing", "not arrived", "never received"]):
        return "missing", TicketPriority.HIGH
    if any(w in msg for w in ["wrong item", "incorrect"]):
        return "wrong_item", TicketPriority.MEDIUM
    if any(w in msg for w in ["delayed", "late", "not shipped"]):
        return "delayed", TicketPriority.MEDIUM
    if any(w in msg for w in ["charge", "billing", "overcharged"]):
        return "billing", TicketPriority.HIGH
    return "general", TicketPriority.LOW


async def run_ticketing(
    session: CustomerSession,
    user_message: str,
    db,
) -> str:
    if not session.is_verified or not session.customer_id:
        return "I need to verify your identity before creating a support ticket."

    category, priority = infer_category(user_message)
    title = f"{category.replace('_', ' ').title()} Issue"

    ticket = await create_ticket(
        db=db,
        customer_id=session.customer_id,
        title=title,
        description=user_message,
        priority=priority,
        category=category,
        order_id=session.current_order_id,
    )

    session.current_ticket_id = ticket.id

    # Send confirmation email
    try:
        await send_ticket_confirmation(
            to_email=session.customer_email,
            customer_name=session.customer_name,
            ticket_id=ticket.id,
            ticket_title=title,
            priority=priority.value,
        )
    except Exception:
        pass

    priority_label = {
        TicketPriority.LOW: "standard",
        TicketPriority.MEDIUM: "medium priority",
        TicketPriority.HIGH: "high priority",
        TicketPriority.CRITICAL: "critical",
    }[priority]

    return (
        f"I've created a {priority_label} support ticket for your issue. "
        f"Ticket ID: {ticket.id}. "
        "You'll receive a confirmation email shortly, and our team will follow up with you. "
        "Is there anything else I can help you with?"
    )
