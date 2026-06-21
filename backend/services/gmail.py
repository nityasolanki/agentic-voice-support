"""
Gmail API service for sending support emails.
"""
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pathlib import Path

from config.settings import get_settings

settings = get_settings()

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

_service = None


def get_gmail_service():
    global _service
    if _service:
        return _service

    creds = None
    token_path = Path(settings.gmail_token_path)
    creds_path = Path(settings.gmail_credentials_path)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token:
            token.write(creds.to_json())

    _service = build("gmail", "v1", credentials=creds)
    return _service


def _build_message(to: str, subject: str, body_html: str, body_text: str) -> dict:
    message = MIMEMultipart("alternative")
    message["to"] = to
    message["from"] = settings.gmail_sender_email
    message["subject"] = subject
    message.attach(MIMEText(body_text, "plain"))
    message.attach(MIMEText(body_html, "html"))

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {"raw": raw}


async def send_ticket_confirmation(
    to_email: str,
    customer_name: str,
    ticket_id: str,
    ticket_title: str,
    priority: str,
):
    subject = f"Support Ticket Created: {ticket_id}"
    body_text = (
        f"Hi {customer_name},\n\n"
        f"Your support ticket has been created.\n\n"
        f"Ticket ID: {ticket_id}\n"
        f"Issue: {ticket_title}\n"
        f"Priority: {priority.upper()}\n\n"
        f"Our team will be in touch shortly.\n\n"
        f"— Support Team"
    )
    body_html = f"""
    <p>Hi <strong>{customer_name}</strong>,</p>
    <p>Your support ticket has been created successfully.</p>
    <table>
      <tr><td><strong>Ticket ID</strong></td><td>{ticket_id}</td></tr>
      <tr><td><strong>Issue</strong></td><td>{ticket_title}</td></tr>
      <tr><td><strong>Priority</strong></td><td>{priority.upper()}</td></tr>
    </table>
    <p>Our team will be in touch shortly.</p>
    <p>— Support Team</p>
    """
    _send(to_email, subject, body_html, body_text)


async def send_refund_confirmation(
    to_email: str,
    customer_name: str,
    refund_id: str,
    order_id: str,
    amount: float,
):
    subject = f"Refund Request Submitted: {refund_id}"
    body_text = (
        f"Hi {customer_name},\n\n"
        f"Your refund request has been submitted.\n\n"
        f"Refund ID: {refund_id}\n"
        f"Order: {order_id}\n"
        f"Amount: ${amount:.2f}\n\n"
        f"Processing typically takes 3-5 business days.\n\n"
        f"— Support Team"
    )
    body_html = f"""
    <p>Hi <strong>{customer_name}</strong>,</p>
    <p>Your refund request has been submitted.</p>
    <table>
      <tr><td><strong>Refund ID</strong></td><td>{refund_id}</td></tr>
      <tr><td><strong>Order</strong></td><td>{order_id}</td></tr>
      <tr><td><strong>Amount</strong></td><td>${amount:.2f}</td></tr>
    </table>
    <p>Processing typically takes 3–5 business days.</p>
    <p>— Support Team</p>
    """
    _send(to_email, subject, body_html, body_text)


def _send(to: str, subject: str, body_html: str, body_text: str):
    service = get_gmail_service()
    message = _build_message(to, subject, body_html, body_text)
    service.users().messages().send(userId="me", body=message).execute()
