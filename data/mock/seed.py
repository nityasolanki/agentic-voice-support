"""
Seed script — generates demo data:
  - 1,000 customers
  - 5,000 orders
  - 500 support tickets
  - Loads knowledge base docs into Qdrant
"""
import asyncio
import random
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from faker import Faker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from backend.db.models import (
    Base, Customer, Product, Order, OrderItem, SupportTicket,
    OrderStatus, TicketPriority, TicketStatus
)
from backend.services.qdrant import upsert_document, ensure_collections
from config.settings import get_settings

fake = Faker()
settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

PRODUCTS = [
    ("PRD-001", "Wireless Headphones", 79.99, "electronics"),
    ("PRD-002", "Laptop Stand", 34.99, "accessories"),
    ("PRD-003", "Mechanical Keyboard", 129.99, "electronics"),
    ("PRD-004", "USB-C Hub", 49.99, "accessories"),
    ("PRD-005", "Webcam HD", 69.99, "electronics"),
    ("PRD-006", "Desk Lamp", 29.99, "home"),
    ("PRD-007", "Mouse Pad XL", 19.99, "accessories"),
    ("PRD-008", "Cable Organizer", 12.99, "accessories"),
]

CARRIERS = ["FedEx", "UPS", "USPS", "DHL"]
CATEGORIES = ["shipping", "billing", "product_issue", "account", "general"]


async def seed_products(db: AsyncSession):
    for pid, name, price, cat in PRODUCTS:
        db.add(Product(id=pid, name=name, price=price, category=cat, sku=f"SKU-{pid}"))
    await db.commit()
    print(f"✓ Seeded {len(PRODUCTS)} products")


async def seed_customers(db: AsyncSession, count: int = 1000) -> list[str]:
    ids = []
    batch = []
    for _ in range(count):
        cid = str(uuid.uuid4())
        ids.append(cid)
        batch.append(Customer(
            id=cid,
            email=fake.unique.email(),
            name=fake.name(),
            phone=fake.phone_number()[:20],
            address=fake.address(),
        ))
        if len(batch) >= 100:
            db.add_all(batch)
            await db.commit()
            batch = []
    if batch:
        db.add_all(batch)
        await db.commit()
    print(f"✓ Seeded {count} customers")
    return ids


async def seed_orders(db: AsyncSession, customer_ids: list[str], count: int = 5000):
    product_ids = [p[0] for p in PRODUCTS]
    statuses = list(OrderStatus)
    batch = []

    for _ in range(count):
        cid = random.choice(customer_ids)
        status = random.choice(statuses)
        created = fake.date_time_between(start_date="-1y", end_date="now", tzinfo=timezone.utc)
        eta = created + timedelta(days=random.randint(3, 14))
        delivered_at = eta + timedelta(hours=random.randint(-12, 48)) if status == OrderStatus.DELIVERED else None

        oid = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order = Order(
            id=oid,
            customer_id=cid,
            status=status,
            total_amount=round(random.uniform(15, 350), 2),
            tracking_number=fake.bothify("1Z#######"),
            carrier=random.choice(CARRIERS),
            estimated_delivery=eta,
            delivered_at=delivered_at,
            created_at=created,
        )
        batch.append(order)

        # Add 1-3 items
        for _ in range(random.randint(1, 3)):
            batch.append(OrderItem(
                order_id=oid,
                product_id=random.choice(product_ids),
                quantity=random.randint(1, 3),
                unit_price=round(random.uniform(10, 130), 2),
            ))

        if len(batch) >= 200:
            db.add_all(batch)
            await db.commit()
            batch = []

    if batch:
        db.add_all(batch)
        await db.commit()
    print(f"✓ Seeded {count} orders")


async def seed_tickets(db: AsyncSession, customer_ids: list[str], count: int = 500):
    batch = []
    for _ in range(count):
        batch.append(SupportTicket(
            id=f"TKT-{uuid.uuid4().hex[:8].upper()}",
            customer_id=random.choice(customer_ids),
            title=fake.sentence(nb_words=6),
            description=fake.paragraph(),
            priority=random.choice(list(TicketPriority)),
            status=random.choice(list(TicketStatus)),
            category=random.choice(CATEGORIES),
            created_at=fake.date_time_between(start_date="-90d", end_date="now", tzinfo=timezone.utc),
        ))
    db.add_all(batch)
    await db.commit()
    print(f"✓ Seeded {count} support tickets")


async def seed_knowledge_base():
    await ensure_collections()
    docs_dir = Path(__file__).parent.parent / "vector"

    for doc_path in docs_dir.glob("*.md"):
        text = doc_path.read_text()
        # Chunk into paragraphs
        chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 50]
        for i, chunk in enumerate(chunks):
            await upsert_document(
                text=chunk,
                metadata={"source": doc_path.name, "chunk": i},
                doc_id=f"{doc_path.stem}-{i}",
            )
        print(f"✓ Indexed {len(chunks)} chunks from {doc_path.name}")


async def main():
    print("🌱 Starting database seed...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as db:
        await seed_products(db)
        customer_ids = await seed_customers(db, 1000)
        await seed_orders(db, customer_ids, 5000)
        await seed_tickets(db, customer_ids, 500)

    print("📚 Indexing knowledge base into Qdrant...")
    await seed_knowledge_base()
    print("✅ Seed complete!")


if __name__ == "__main__":
    asyncio.run(main())
