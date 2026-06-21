from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_order_by_id, get_orders_by_customer

router = APIRouter()


@router.get("/{order_id}")
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    order = await get_order_by_id(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "id": order.id,
        "status": order.status,
        "total_amount": order.total_amount,
        "tracking_number": order.tracking_number,
        "carrier": order.carrier,
        "estimated_delivery": order.estimated_delivery,
        "delivered_at": order.delivered_at,
    }


@router.get("/customer/{customer_id}")
async def get_customer_orders(customer_id: str, db: AsyncSession = Depends(get_db)):
    orders = await get_orders_by_customer(db, customer_id)
    return [
        {"id": o.id, "status": o.status, "total_amount": o.total_amount, "created_at": o.created_at}
        for o in orders
    ]
