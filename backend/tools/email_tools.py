"""Email notification tools via Gmail API."""
from __future__ import annotations
import base64
from email.mime.text import MIMEText
from langchain_core.tools import tool

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import get_settings

settings = get_settings()


def _get_gmail_service():
    """Build an authenticated Gmail service client."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        import pickle

        SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
        creds = None
        token_file = "config/token.pickle"

        if os.path.exists(token_file):
            with open(token_file, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    settings.gmail_credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(token_file, "wb") as f:
                pickle.dump(creds, f)

        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        return None  # Gracefully degrade in demo mode


def _send_email(to: str, subject: str, body: str) -> dict:
    service = _get_gmail_service()
    if not service:
        # Demo mode: log instead of send
        print(f"[EMAIL DEMO] To: {to} | Subject: {subject}\n{body}")
        return {"success": True, "demo": True, "message": f"Email would be sent to {to}"}

    message = MIMEText(body, "html")
    message["to"] = to
    message["from"] = settings.gmail_sender_email
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"success": True, "message": f"Email sent to {to}"}


@tool
def send_ticket_confirmation(customer_email: str, ticket_number: str, subject: str, priority: str) -> dict:
    """Send a support ticket confirmation email to the customer."""
    body = f"""
    <h2>Support Ticket Created</h2>
    <p>Your support request has been received. Here are your ticket details:</p>
    <table>
      <tr><td><strong>Ticket Number:</strong></td><td>{ticket_number}</td></tr>
      <tr><td><strong>Subject:</strong></td><td>{subject}</td></tr>
      <tr><td><strong>Priority:</strong></td><td>{priority.upper()}</td></tr>
      <tr><td><strong>Status:</strong></td><td>OPEN</td></tr>
    </table>
    <p>Our team will review your request and respond within 24 hours.</p>
    """
    return _send_email(customer_email, f"Support Ticket {ticket_number} Created", body)


@tool
def send_refund_confirmation(customer_email: str, refund_number: str, amount: float, order_number: str) -> dict:
    """Send a refund confirmation email to the customer."""
    body = f"""
    <h2>Refund Request Submitted</h2>
    <p>Your refund has been successfully submitted. Details below:</p>
    <table>
      <tr><td><strong>Refund Number:</strong></td><td>{refund_number}</td></tr>
      <tr><td><strong>Order Number:</strong></td><td>{order_number}</td></tr>
      <tr><td><strong>Refund Amount:</strong></td><td>${amount:.2f}</td></tr>
    </table>
    <p>Refunds take 5–7 business days to appear on your original payment method.</p>
    """
    return _send_email(customer_email, f"Refund {refund_number} Confirmed", body)


@tool
def send_order_update(customer_email: str, order_number: str, status: str, tracking_number: str | None = None) -> dict:
    """Send an order status update email to the customer."""
    tracking_html = f"<tr><td><strong>Tracking #:</strong></td><td>{tracking_number}</td></tr>" if tracking_number else ""
    body = f"""
    <h2>Order Update — {order_number}</h2>
    <table>
      <tr><td><strong>Order Number:</strong></td><td>{order_number}</td></tr>
      <tr><td><strong>New Status:</strong></td><td>{status.upper()}</td></tr>
      {tracking_html}
    </table>
    <p>Thank you for shopping with us!</p>
    """
    return _send_email(customer_email, f"Order {order_number} Update: {status}", body)
