"""Tools for customer verification and profile retrieval."""
from __future__ import annotations
from langchain_core.tools import tool
from sqlalchemy.orm import Session
from sqlalchemy import select

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend.db.models import Customer
from backend.db.session import sync_engine


def _get_session():
    return Session(sync_engine)


@tool
def verify_customer_by_email(email: str) -> dict:
    """Verify a customer's identity by email address. Returns customer profile if found."""
    with _get_session() as db:
        customer = db.scalar(select(Customer).where(Customer.email == email.lower().strip()))
        if not customer:
            return {"verified": False, "error": "No account found with that email address."}
        return {
            "verified": True,
            "customer_id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "subscription_active": customer.subscription_active,
            "subscription_plan": customer.subscription_plan,
        }


@tool
def get_customer_profile(customer_id: int) -> dict:
    """Get full customer profile by customer ID."""
    with _get_session() as db:
        customer = db.get(Customer, customer_id)
        if not customer:
            return {"error": f"Customer {customer_id} not found."}
        return {
            "customer_id": customer.id,
            "name": customer.name,
            "email": customer.email,
            "phone": customer.phone,
            "address": customer.address,
            "subscription_active": customer.subscription_active,
            "subscription_plan": customer.subscription_plan,
        }


@tool
def cancel_subscription(customer_id: int) -> dict:
    """Cancel a customer's subscription."""
    with _get_session() as db:
        customer = db.get(Customer, customer_id)
        if not customer:
            return {"error": f"Customer {customer_id} not found."}
        if not customer.subscription_active:
            return {"success": False, "message": "No active subscription found."}
        customer.subscription_active = False
        db.commit()
        return {
            "success": True,
            "message": f"Subscription cancelled for {customer.name}. "
                       "Access continues until the end of the current billing period.",
        }
