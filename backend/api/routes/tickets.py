from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from backend.db.session import get_db
from backend.db.crud import get_open_tickets, update_ticket_status
from backend.db.models import TicketStatus

router = APIRouter()


@router.get("/open")
async def list_open_tickets(db: AsyncSession = Depends(get_db)):
    tickets = await get_open_tickets(db)
    return [
        {
            "id": t.id,
            "customer_id": t.customer_id,
            "title": t.title,
            "priority": t.priority,
            "status": t.status,
            "created_at": t.created_at,
        }
        for t in tickets
    ]


@router.patch("/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: str,
    resolution_notes: str = "",
    db: AsyncSession = Depends(get_db),
):
    ticket = await update_ticket_status(
        db, ticket_id, TicketStatus.RESOLVED, resolution_notes
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"id": ticket.id, "status": ticket.status}
