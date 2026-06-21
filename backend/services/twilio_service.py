"""
Twilio outbound calling service.
"""
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Say, Gather
from config.settings import get_settings

settings = get_settings()

_client = None


def get_twilio_client() -> Client:
    global _client
    if _client is None:
        _client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    return _client


async def make_outbound_call(
    to_number: str,
    message: str,
    customer_id: str,
    reason: str = "support_followup",
) -> dict:
    """
    Initiate an outbound call with a TwiML message.
    Returns call SID and status.
    """
    client = get_twilio_client()

    # Build TwiML
    response = VoiceResponse()
    response.say(message, voice="Polly.Joanna", language="en-US")
    response.say(
        "Press 1 to speak with support, or press 2 to receive a follow-up email.",
        voice="Polly.Joanna",
    )

    gather = Gather(num_digits=1, action=f"{settings.twilio_webhook_base_url}/api/outbound/response")
    response.append(gather)
    response.say("We didn't receive your input. Goodbye.", voice="Polly.Joanna")

    call = client.calls.create(
        to=to_number,
        from_=settings.twilio_from_number,
        twiml=str(response),
        status_callback=f"{settings.twilio_webhook_base_url}/api/outbound/status",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )

    return {
        "call_sid": call.sid,
        "status": call.status,
        "to": to_number,
        "reason": reason,
        "customer_id": customer_id,
    }


async def get_call_status(call_sid: str) -> dict:
    client = get_twilio_client()
    call = client.calls(call_sid).fetch()
    return {
        "call_sid": call.sid,
        "status": call.status,
        "duration": call.duration,
        "direction": call.direction,
    }


def build_delay_notification_message(customer_name: str, order_id: str, new_eta: str) -> str:
    return (
        f"Hello, this is an automated message from customer support. "
        f"We're calling to let you know that your order {order_id} has been delayed. "
        f"Your new estimated delivery date is {new_eta}. "
        f"We apologize for the inconvenience."
    )


def build_ticket_followup_message(customer_name: str, ticket_id: str) -> str:
    return (
        f"Hello {customer_name}, this is a follow-up call regarding your support ticket "
        f"{ticket_id}. We wanted to check if your issue has been resolved "
        f"and if there is anything else we can help you with."
    )
