from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from google.cloud import firestore

from app.core.firebase import db
from app.core.security import get_current_user, get_admin_user

router = APIRouter()

# --- PYDANTIC MODELS ---
class TicketCreate(BaseModel):
    subject: str
    description: str

class AdminTicketReply(BaseModel):
    status: str # e.g., "open", "in_progress", "resolved", "closed"
    admin_response: str


# ==========================================
# 🙋‍♂️ USER ROUTES (Anyone logged in)
# ==========================================

@router.post("/create", tags=["Support Tickets"])
async def create_support_ticket(
    ticket: TicketCreate, 
    user: dict = Depends(get_current_user) # 🛡️ Base Door: Anyone can ask for help
):
    """Allows any logged-in user (Student, Shop, or Guest) to raise an issue."""
    try:
        uid = user.get("uid")
        
        ticket_data = ticket.model_dump()
        ticket_data["user_id"] = uid
        ticket_data["user_email"] = user.get("email") # Helpful for the admin to see
        ticket_data["status"] = "open"
        ticket_data["admin_response"] = None
        ticket_data["created_at"] = firestore.SERVER_TIMESTAMP
        ticket_data["updated_at"] = firestore.SERVER_TIMESTAMP
        
        # Save to a completely isolated collection
        doc_ref = db.collection("support_tickets").document()
        doc_ref.set(ticket_data)
        
        return {"message": "Support ticket submitted successfully!", "ticket_id": doc_ref.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/my-tickets", tags=["Support Tickets"])
async def get_my_tickets(user: dict = Depends(get_current_user)):
    """Allows a user to view the status and admin replies for their own tickets."""
    try:
        uid = user.get("uid")
        
        # Only fetch tickets that belong to this specific user
        tickets_query = db.collection("support_tickets").where("user_id", "==", uid).order_by("created_at", direction=firestore.Query.DESCENDING).stream()
        
        results = [{"id": doc.id, **doc.to_dict()} for doc in tickets_query]
        return {"data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 👑 ADMIN ROUTES (Strictly God Mode)
# ==========================================

@router.get("/admin/all", tags=["Admin Control Panel"])
async def get_all_campus_tickets(
    status: Optional[str] = None, 
    admin: dict = Depends(get_admin_user) # 🛡️ STRICT DOOR: Admins ONLY!
):
    """Allows an admin to view all support tickets, optionally filtering by status."""
    try:
        query = db.collection("support_tickets").order_by("created_at", direction=firestore.Query.DESCENDING)
        
        if status:
            query = query.where("status", "==", status)
            
        docs = query.stream()
        return {"data": [{"id": doc.id, **doc.to_dict()} for doc in docs]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/{ticket_id}/reply", tags=["Admin Control Panel"])
async def reply_to_ticket(
    ticket_id: str, 
    reply: AdminTicketReply, 
    admin: dict = Depends(get_admin_user) # 🛡️ STRICT DOOR: Admins ONLY!
):
    """Allows an admin to update a ticket's status and send a message back to the user."""
    try:
        ticket_ref = db.collection("support_tickets").document(ticket_id)
        
        if not ticket_ref.get().exists:
            raise HTTPException(status_code=404, detail="Ticket not found.")
            
        # Update the ticket with the admin's response and the new status
        ticket_ref.update({
            "status": reply.status,
            "admin_response": reply.admin_response,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "resolved_by": admin.get("email") # Keep track of which admin helped
        })
        
        return {"message": f"Ticket {ticket_id} marked as {reply.status}."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))