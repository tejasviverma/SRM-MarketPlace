from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore

from app.core.firebase import db
from app.core.security import get_marketplace_user
from app.models.chat import BidInitiate, ChatMessage, BidStatus

router = APIRouter()

@router.post("/initiate", tags=["Bidding & Chat"])
async def initiate_bid_chat(
    bid: BidInitiate, 
    user: dict = Depends(get_marketplace_user) 
):
    """
    Initiates a chat room. 
    Allows bidding for student-to-student transactions.
    Forces standard messaging (no bidding) for student-to-shop queries.
    """
    sender_id = user.get("uid")
    
    if sender_id == bid.owner_id:
        raise HTTPException(status_code=400, detail="You cannot message yourself.")

    try:
        # 🛡️ THE NEW RULE: Check who we are talking to!
        owner_doc = db.collection("users").document(bid.owner_id).get()
        if not owner_doc.exists:
            raise HTTPException(status_code=404, detail="The owner of this listing no longer exists.")
            
        owner_role = owner_doc.to_dict().get("role", "student")
        
        # If the target is a business, and the user tried to submit a bid, block it!
        if owner_role == "shop" and bid.bid_amount is not None:
            raise HTTPException(
                status_code=400, 
                detail="Bidding is disabled for verified campus shops. Please send a direct message instead."
            )

        # --- Proceed with Room Creation ---
        participants = sorted([sender_id, bid.owner_id])
        room_id = f"{bid.listing_id}_{participants[0]}_{participants[1]}"
        room_ref = db.collection("chat_rooms").document(room_id)
        
        room_data = {
            "listing_id": bid.listing_id,
            "participants": participants,
            "last_message": bid.initial_message,
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        room_ref.set(room_data, merge=True)
        
        validated_message = ChatMessage(
            sender_id=sender_id,
            text=bid.initial_message,
            is_bid=bid.bid_amount is not None,
            bid_amount=bid.bid_amount,
            bid_status=BidStatus.PENDING if bid.bid_amount is not None else None 
        )
        
        message_data = validated_message.model_dump()
        message_data["timestamp"] = firestore.SERVER_TIMESTAMP 
        
        room_ref.collection("messages").add(message_data)
        
        return {
            "message": "Message sent successfully!" if bid.bid_amount is None else "Bid submitted successfully!", 
            "room_id": room_id
        }

    except HTTPException:
        raise # Pass through our custom 400 errors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inbox", tags=["Bidding & Chat"])
async def get_user_inbox(user: dict = Depends(get_marketplace_user)):
    """
    Fetches all active chat rooms for the logged-in user to display in their inbox.
    """
    try:
        uid = user.get("uid")
        
        rooms_query = db.collection("chat_rooms").where(
            "participants", "array_contains", uid
        ).order_by("updated_at", direction=firestore.Query.DESCENDING).get()
        
        inbox = []
        for room in rooms_query:
            room_dict = room.to_dict()
            inbox.append({
                "room_id": room.id,
                "listing_id": room_dict.get("listing_id"),
                "last_message": room_dict.get("last_message"),
                "other_user_id": [p for p in room_dict.get("participants") if p != uid][0]
            })
            
        return {"data": inbox}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# 🆕 THE NEW ROUTE: Handles ongoing negotiation and regular texting
@router.post("/{room_id}/messages", tags=["Bidding & Chat"])
async def send_message_to_room(
    room_id: str,
    message: ChatMessage, 
    user: dict = Depends(get_marketplace_user)
):
    """Allows users to send standard texts OR new counter-offers into an existing chat."""
    try:
        uid = user.get("uid")
        room_ref = db.collection("chat_rooms").document(room_id)
        room_doc = room_ref.get()
        
        # 1. Security Check: Does the room exist and is this user allowed in it?
        if not room_doc.exists:
            raise HTTPException(status_code=404, detail="Chat room not found.")
            
        if uid not in room_doc.to_dict().get("participants", []):
            raise HTTPException(status_code=403, detail="You are not a participant in this chat.")
            
        # 2. Prepare the new message payload
        msg_data = message.model_dump()
        msg_data["sender_id"] = uid
        msg_data["timestamp"] = firestore.SERVER_TIMESTAMP
        
        # If the user is submitting a new counter-offer bid, set it to pending
        if message.is_bid:
            msg_data["bid_status"] = BidStatus.PENDING
            
        # 3. Save the message to the subcollection
        room_ref.collection("messages").add(msg_data)
        
        # 4. Update the room's preview text so the inbox updates instantly
        room_ref.update({
            "last_message": message.text,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        
        return {"message": "Sent successfully!"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{room_id}/messages/{message_id}/accept", tags=["Bidding & Chat"])
async def accept_bid(
    room_id: str,
    message_id: str,
    user: dict = Depends(get_marketplace_user)
):
    """
    Allows a seller to accept a specific bid. 
    This automatically changes the item status to 'sold' and removes it from the live feed.
    """
    try:
        uid = user.get("uid")
        
        # 1. Locate the chat room to find which listing they are talking about
        room_ref = db.collection("chat_rooms").document(room_id)
        room_doc = room_ref.get()
        
        if not room_doc.exists:
            raise HTTPException(status_code=404, detail="Chat room not found.")
            
        listing_id = room_doc.to_dict().get("listing_id")
        
        # 2. Locate the listing to verify the user actually owns it!
        listing_ref = db.collection("listings").document(listing_id)
        listing_doc = listing_ref.get()
        
        if not listing_doc.exists:
            raise HTTPException(status_code=404, detail="Listing not found.")
            
        if listing_doc.to_dict().get("owner_id") != uid:
            raise HTTPException(status_code=403, detail="Security Error: Only the seller can accept a bid.")
            
        # 3. THE MAGIC LIFECYCLE CHANGE: Mark the listing as SOLD
        # This instantly hides it from the `get_live_products` query you built!
        listing_ref.update({"status": "sold"})
        
        # 4. Mark the specific bid message inside the chat as ACCEPTED
        message_ref = room_ref.collection("messages").document(message_id)
        message_ref.update({"bid_status": "accepted"})
        
        return {
            "message": "Bid accepted! The item is now marked as sold and hidden from the marketplace.",
            "listing_id": listing_id
        }
        
    except HTTPException:
        raise # Pass through our custom 403 and 404 errors
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))