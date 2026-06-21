from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.agents.outbound_calling import notify_delayed_orders, follow_up_open_tickets

router = APIRouter()


@router.post("/trigger-delay-notifications")
async def trigger_delay_notifications(db: AsyncSession = Depends(get_db)):
    """Manually trigger outbound calls for delayed orders."""
    results = await notify_delayed_orders(db)
    return {"triggered": len(results), "results": results}


@router.post("/trigger-ticket-followups")
async def trigger_ticket_followups(db: AsyncSession = Depends(get_db)):
    """Manually trigger follow-up calls for stale open tickets."""
    results = await follow_up_open_tickets(db)
    return {"triggered": len(results), "results": results}


@router.post("/response")
async def handle_call_response(request: Request):
    """Twilio webhook: handle digit pressed during outbound call."""
    form = await request.form()
    digits = form.get("Digits", "")

    from twilio.twiml.voice_response import VoiceResponse
    response = VoiceResponse()

    if digits == "1":
        response.say("Connecting you to our support team now. Please hold.", voice="Polly.Joanna")
    elif digits == "2":
        response.say("We'll send a follow-up email shortly. Thank you, goodbye.", voice="Polly.Joanna")
    else:
        response.say("We didn't get a valid selection. Goodbye.", voice="Polly.Joanna")

    return response.to_xml()


@router.post("/status")
async def call_status_webhook(request: Request):
    """Twilio status callback webhook."""
    form = await request.form()
    call_sid = form.get("CallSid")
    status = form.get("CallStatus")
    # In production: update call log in DB here
    return {"received": True, "call_sid": call_sid, "status": status}
