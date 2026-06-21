"""Twilio outbound calling tools."""
from __future__ import annotations
from langchain_core.tools import tool

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import get_settings

settings = get_settings()


def _get_twilio_client():
    try:
        from twilio.rest import Client
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            return None
        return Client(settings.twilio_account_sid, settings.twilio_auth_token)
    except ImportError:
        return None

@tool
def initiate_outbound_call(customer_phone: str, message: str, customer_id: int) -> dict:
    """Initiate an outbound call to a customer via Twilio."""
    client = _get_twilio_client()
    if not client:
        print(f"[TWILIO DEMO] Would call {customer_phone}: {message}")
        return {"success": True, "demo": True}

    try:
        call = client.calls.create(
            to=customer_phone,
            from_=settings.twilio_from_number,
            url=f"{settings.twilio_webhook_base_url}/twilio/outbound-twiml",
        )
        return {
            "success": True,
            "call_sid": call.sid,
            "status": call.status,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

# @tool
# def initiate_outbound_call(customer_phone: str, message: str, customer_id: int) -> dict:
#     """Initiate an outbound call to a customer via Twilio with a TwiML message."""
#     client = _get_twilio_client()
#     if not client:
#         print(f"[TWILIO DEMO] Would call {customer_phone}: {message}")
#         return {
#             "success": True,
#             "demo": True,
#             "message": f"Outbound call would be initiated to {customer_phone}",
#         }

#     # Build TwiML — the Twilio webhook serves a TwiML response
#     webhook_url = f"{settings.twilio_webhook_base_url}/twilio/outbound-twiml"
#     try:
#         call = client.calls.create(
#             to=customer_phone,
#             from_=settings.twilio_from_number,
#             url=webhook_url,
#         )
#         return {
#             "success": True,
#             "call_sid": call.sid,
#             "status": call.status,
#             "message": f"Outbound call initiated to {customer_phone}",
#         }
#     except Exception as e:
#         return {"success": False, "error": str(e)}


@tool
def send_sms_notification(customer_phone: str, message: str) -> dict:
    """Send an SMS notification to a customer via Twilio."""
    client = _get_twilio_client()
    if not client:
        print(f"[TWILIO DEMO] SMS to {customer_phone}: {message}")
        return {"success": True, "demo": True, "message": f"SMS would be sent to {customer_phone}"}
    try:
        msg = client.messages.create(
            to=customer_phone,
            from_=settings.twilio_from_number,
            body=message,
        )
        return {"success": True, "message_sid": msg.sid}
    except Exception as e:
        return {"success": False, "error": str(e)}
