"""
Seed script — generates 1,000 customers, 5,000 orders, 500 tickets,
and populates Qdrant with FAQ / policy documents.

Run: python -m db.seed
"""
import random
import uuid
from datetime import datetime, timedelta
from faker import Faker
from sqlalchemy.orm import Session

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.db.models import (
    Base, Customer, Product, Order, OrderItem,
    SupportTicket, Refund, CallLog,
    OrderStatus, TicketStatus, TicketPriority, RefundStatus
)
from backend.db.session import sync_engine
from backend.memory.vector_store import VectorStore

fake = Faker()
random.seed(42)

# ─── Products ───────────────────────────────────────────────
PRODUCTS = [
    {"name": "Wireless Headphones Pro", "sku": "WHP-001", "price": 149.99, "category": "Electronics"},
    {"name": "Ergonomic Office Chair", "sku": "EOC-002", "price": 399.99, "category": "Furniture"},
    {"name": "Smart Watch Series X", "sku": "SWX-003", "price": 299.99, "category": "Electronics"},
    {"name": "Running Shoes Ultra", "sku": "RSU-004", "price": 89.99, "category": "Footwear"},
    {"name": "Coffee Maker Deluxe", "sku": "CMD-005", "price": 79.99, "category": "Appliances"},
    {"name": "Laptop Backpack 30L", "sku": "LBP-006", "price": 59.99, "category": "Bags"},
    {"name": "Bluetooth Speaker Mini", "sku": "BSM-007", "price": 49.99, "category": "Electronics"},
    {"name": "Yoga Mat Premium", "sku": "YMP-008", "price": 34.99, "category": "Fitness"},
    {"name": "Mechanical Keyboard RGB", "sku": "MKR-009", "price": 129.99, "category": "Electronics"},
    {"name": "Air Purifier HEPA", "sku": "APH-010", "price": 199.99, "category": "Appliances"},
]

CARRIERS = ["FedEx", "UPS", "USPS", "DHL", "Amazon Logistics"]
TICKET_CATEGORIES = ["shipping", "refund", "product_quality", "subscription", "account", "billing"]
TICKET_SUBJECTS = {
    "shipping": ["Order not arrived", "Wrong delivery address", "Package damaged in transit"],
    "refund": ["Request refund for order", "Refund not received", "Partial refund request"],
    "product_quality": ["Product arrived damaged", "Item not as described", "Missing parts"],
    "subscription": ["Cancel subscription", "Subscription renewal issue", "Change subscription plan"],
    "account": ["Cannot login", "Update account details", "Delete account request"],
    "billing": ["Charged twice", "Invoice not received", "Wrong amount charged"],
}

# ─── Knowledge Base Documents ────────────────────────────────
KB_DOCUMENTS = [
    {
        "title": "Return & Refund Policy",
        "content": """Our return policy allows customers to return items within 30 days of delivery.
Items must be in original condition with packaging. To initiate a return, contact support
with your order number. Refunds are processed within 5-7 business days to the original
payment method. Digital products and personalized items are non-refundable.
Sale items can be exchanged but not refunded."""
    },
    {
        "title": "Shipping Policy",
        "content": """Standard shipping takes 5-7 business days. Express shipping (2-3 days) is
available for an additional fee. Free shipping on orders over $50. International shipping
takes 10-14 business days. Tracking information is emailed once the order ships.
We ship to all 50 US states and 30+ countries. Orders placed before 2 PM EST ship same day."""
    },
    {
        "title": "Subscription Plans FAQ",
        "content": """We offer three subscription tiers: Basic ($9.99/mo), Pro ($19.99/mo), and
Enterprise ($49.99/mo). Subscriptions auto-renew monthly. Cancel anytime before the renewal
date for no charge. Downgrading takes effect next billing cycle. Upgrades are immediate with
prorated billing. Annual plans receive a 20% discount."""
    },
    {
        "title": "Warranty Information",
        "content": """All electronics come with a 1-year manufacturer warranty. Extended warranty
plans are available for purchase. Warranty covers manufacturing defects but not accidental
damage. To file a warranty claim, provide proof of purchase and photos of the defect.
Warranty replacements ship within 3-5 business days."""
    },
    {
        "title": "Order Cancellation Policy",
        "content": """Orders can be cancelled within 1 hour of placement for a full refund.
After 1 hour, cancellation is subject to processing status. Shipped orders cannot be
cancelled but can be returned. Subscription cancellations take effect at the end of the
current billing period. Contact support immediately to request a cancellation."""
    },
    {
        "title": "Customer Support Hours",
        "content": """Our AI support agent is available 24/7. Human support agents are available
Monday-Friday 9AM-6PM EST. Response time for email tickets is within 24 hours.
Phone support is available during business hours. Priority support is included in Pro and
Enterprise plans with guaranteed 4-hour response times."""
    },
    {
        "title": "Payment & Billing FAQ",
        "content": """We accept Visa, Mastercard, American Express, PayPal, and Apple Pay.
Invoices are emailed after each purchase. You can view billing history in your account portal.
Disputed charges must be reported within 60 days. We use 256-bit SSL encryption for all
transactions. Payment information is never stored on our servers."""
    },
    {
        "title": "Account Management",
        "content": """To reset your password, click 'Forgot Password' on the login page.
Account details can be updated in Profile Settings. To delete your account, contact support
with your email address. Account data is retained for 90 days after deletion per our privacy
policy. Two-factor authentication is available and recommended for all accounts."""
    },
]


def seed_database():
    print("Creating tables...")
    Base.metadata.create_all(sync_engine)

    with Session(sync_engine) as session:
        # Products
        print("Seeding products...")
        products = []
        for p in PRODUCTS:
            prod = Product(**p, description=fake.sentence(nb_words=10))
            session.add(prod)
            products.append(prod)
        session.flush()

        # Customers
        print("Seeding 1,000 customers...")
        customers = []
        for _ in range(1000):
            c = Customer(
                email=fake.unique.email(),
                name=fake.name(),
                phone=fake.phone_number()[:20],
                address=fake.address().replace("\n", ", "),
                subscription_active=random.random() > 0.6,
                subscription_plan=random.choice(["basic", "pro", "enterprise", None]),
            )
            session.add(c)
            customers.append(c)
        session.flush()

        # Orders
        print("Seeding 5,000 orders...")
        orders = []
        for i in range(5000):
            customer = random.choice(customers)
            status = random.choice(list(OrderStatus))
            created = fake.date_time_between(start_date="-1y", end_date="now")
            shipped_at = created + timedelta(days=random.randint(1, 3)) if status not in [OrderStatus.PENDING, OrderStatus.PROCESSING] else None
            estimated = shipped_at + timedelta(days=random.randint(3, 10)) if shipped_at else None
            delivered_at = estimated + timedelta(days=random.randint(-1, 2)) if status == OrderStatus.DELIVERED and estimated else None

            o = Order(
                order_number=f"ORD-{10000 + i}",
                customer_id=customer.id,
                status=status,
                total_amount=round(random.uniform(20, 500), 2),
                tracking_number=fake.bothify("1Z###########") if shipped_at else None,
                carrier=random.choice(CARRIERS) if shipped_at else None,
                estimated_delivery=estimated,
                shipped_at=shipped_at,
                delivered_at=delivered_at,
                created_at=created,
            )
            session.add(o)
            orders.append(o)
        session.flush()

        # Order items
        print("Seeding order items...")
        for order in orders:
            for _ in range(random.randint(1, 3)):
                product = random.choice(products)
                session.add(OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=random.randint(1, 3),
                    unit_price=product.price,
                ))

        # Support Tickets
        print("Seeding 500 support tickets...")
        for i in range(500):
            customer = random.choice(customers)
            category = random.choice(TICKET_CATEGORIES)
            subject = random.choice(TICKET_SUBJECTS[category])
            status = random.choice(list(TicketStatus))
            priority = random.choice(list(TicketPriority))
            created = fake.date_time_between(start_date="-6mo", end_date="now")

            t = SupportTicket(
                ticket_number=f"TKT-{5000 + i}",
                customer_id=customer.id,
                order_id=random.choice(orders).id if random.random() > 0.4 else None,
                status=status,
                priority=priority,
                category=category,
                subject=subject,
                description=fake.paragraph(nb_sentences=3),
                resolution=fake.sentence() if status in [TicketStatus.RESOLVED, TicketStatus.CLOSED] else None,
                created_at=created,
                resolved_at=created + timedelta(days=random.randint(1, 7)) if status == TicketStatus.RESOLVED else None,
            )
            session.add(t)

        # Refunds
        print("Seeding refunds...")
        refund_orders = random.sample(orders, 200)
        for i, order in enumerate(refund_orders):
            session.add(Refund(
                refund_number=f"REF-{8000 + i}",
                order_id=order.id,
                amount=round(order.total_amount * random.uniform(0.3, 1.0), 2),
                reason=random.choice(["Item damaged", "Not as described", "Wrong item", "Changed mind"]),
                status=random.choice(list(RefundStatus)),
                created_at=order.created_at + timedelta(days=random.randint(1, 30)),
            ))

        session.commit()
        print("✅ Database seeded successfully.")

    # Vector store
    print("Seeding Qdrant knowledge base...")
    try:
        vs = VectorStore()
        vs.seed_knowledge_base(KB_DOCUMENTS)
        print("✅ Knowledge base seeded successfully.")
    except Exception as e:
        print(f"⚠️  Qdrant seeding skipped (start docker-compose first): {e}")


if __name__ == "__main__":
    seed_database()
