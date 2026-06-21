import sys
sys.path.insert(0, '.')
from sqlalchemy import text
from backend.db.session import sync_engine

with sync_engine.connect() as conn:
    # First check what enum values actually exist in the DB
    result = conn.execute(text("SELECT unnest(enum_range(NULL::orderstatus))"))
    values = [row[0] for row in result.fetchall()]
    print("Valid orderstatus values:", values)

    # Use the actual values from DB
    shipped = next((v for v in values if 'ship' in v.lower()), values[0])
    delivered = next((v for v in values if 'deliver' in v.lower()), values[0])
    processing = next((v for v in values if 'process' in v.lower()), values[0])

    print(f"Using: shipped='{shipped}' delivered='{delivered}' processing='{processing}'")

    conn.execute(text(f"""
        INSERT INTO orders (order_number, customer_id, status, total_amount, tracking_number, carrier, estimated_delivery, created_at)
        VALUES 
          ('ORD-001', 1001, '{shipped}', 99.99, '1Z999AA10123456784', 'UPS', NOW() + INTERVAL '2 days', NOW() - INTERVAL '3 days'),
          ('ORD-002', 1001, '{delivered}', 149.99, '1Z999AA10123456785', 'FedEx', NOW() - INTERVAL '1 day', NOW() - INTERVAL '7 days'),
          ('ORD-003', 1001, '{processing}', 49.99, NULL, NULL, NOW() + INTERVAL '5 days', NOW() - INTERVAL '1 day')
        ON CONFLICT (order_number) DO UPDATE SET customer_id = EXCLUDED.customer_id
    """))
    conn.commit()

    result = conn.execute(text('SELECT order_number, status FROM orders WHERE customer_id = 1001'))
    rows = result.fetchall()
    print("Inserted orders:")
    for row in rows:
        print(" ", row)