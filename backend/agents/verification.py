"""
Customer Verification Agent.
Confirms customer identity before allowing sensitive operations.
"""
from backend.db.crud import get_customer_by_email
from backend.memory.session import CustomerSession
from backend.services.llm import llm_service
from config.prompts import VERIFICATION_SYSTEM_PROMPT


async def run_verification(
    session: CustomerSession,
    user_message: str,
    db,
) -> str:
    """
    Drive the verification flow.
    Returns a response string and updates session.is_verified when successful.
    """
    # If message looks like an email, attempt lookup
    if "@" in user_message and "." in user_message:
        email = user_message.strip().lower()
        customer = await get_customer_by_email(db, email)

        if customer:
            session.customer_id = customer.id
            session.customer_name = customer.name
            session.customer_email = customer.email
            session.is_verified = True
            session.add_turn("assistant", f"Identity confirmed.", agent="verification")
            return (
                f"Thank you, {customer.name}! I've verified your identity. "
                f"How can I help you today?"
            )
        else:
            return (
                "I couldn't find an account with that email address. "
                "Could you double-check it, or would you like to continue as a guest?"
            )

    # Ask for email if not yet provided
    session.add_turn("assistant", "Asking for email.", agent="verification")
    return (
        "To help you today, I'll need to verify your identity. "
        "Could you please provide the email address associated with your account?"
    )
