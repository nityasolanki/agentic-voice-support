"""
Escalation Agent.
Handles frustrated customers and complex issues.
"""
from backend.db.crud import create_ticket
from backend.db.models import TicketPriority, TicketStatus
from backend.memory.session import CustomerSession


EMPATHY_OPENERS = [
    "I completely understand your frustration, and I sincerely apologize for this experience.",
    "I hear you, and I'm truly sorry this has happened.",
    "Your frustration is completely valid, and I want to make this right.",
]


async def run_escalation(
    session: CustomerSession,
    user_message: str,
    db,
) -> str:
    session.escalated = True

    opener = EMPATHY_OPENERS[len(session.turns) % len(EMPATHY_OPENERS)]

    ticket = None
    if session.is_verified and session.customer_id:
        ticket = await create_ticket(
            db=db,
            customer_id=session.customer_id,
            title="Escalated: Customer Frustration",
            description=f"Customer escalated. Last message: {user_message}",
            priority=TicketPriority.HIGH,
            category="escalated",
            order_id=session.current_order_id,
        )
        session.current_ticket_id = ticket.id if ticket else None

    ticket_info = f" Escalation ticket {ticket.id} has been created." if ticket else ""

    return (
        f"{opener} "
        f"I'm escalating your case to a senior support specialist right now.{ticket_info} "
        "Someone from our team will contact you within 2 hours. "
        "Would you prefer to be contacted by phone or email?"
    )
