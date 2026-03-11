from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore
from pydantic import BaseModel

from app.core.firebase import db
from app.core.security import get_admin_user

router = APIRouter()

# --- Pydantic Models for Admin Requests ---
class RoleUpdate(BaseModel):
    role: str # e.g., 'student', 'shop', 'admin', 'banned'

class TakedownRequest(BaseModel):
    reason: str

class RejectRequest(BaseModel):
    reason: str # 🌟 Added for shop rejections


# --- 🏪 SHOP MODERATION ---

@router.get("/shops/pending", tags=["Admin - Shops"])
async def get_pending_shops(admin: dict = Depends(get_admin_user)):
    """Fetches all shop applications currently awaiting admin approval."""
    try:
        # 🌟 CHANGED: Now queries by the 'pending' status string instead of the boolean
        shops = db.collection("shops").where("status", "==", "pending").stream()
        return {"data": [{"id": shop.id, **shop.to_dict()} for shop in shops]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/shops/{shop_id}/verify", tags=["Admin - Shops"])
async def verify_shop(shop_id: str, admin: dict = Depends(get_admin_user)):
    """
    Approves a shop. 
    Crucially, it updates BOTH the shop's status AND the user's official role in one go.
    """
    try:
        shop_ref = db.collection("shops").document(shop_id)
        if not shop_ref.get().exists:
            raise HTTPException(status_code=404, detail="Shop application not found.")
            
        # 1. Verify the Shop so it appears in the public directory
        # 🌟 CHANGED: Added the "approved" status string and tracking data
        shop_ref.update({
            "is_verified": True,
            "status": "approved",
            "approved_by": admin.get("email"),
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        
        # 2. Promote the User so they unlock the get_verified_shop door
        user_ref = db.collection("users").document(shop_id) # The owner's UID is the shop_id
        if user_ref.get().exists:
            user_ref.update({"role": "shop"})
            
        return {"message": f"Shop {shop_id} officially verified and user promoted to 'shop'!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 🌟 NEW ENDPOINT: Rejecting a Shop Application
@router.put("/shops/{shop_id}/reject", tags=["Admin - Shops"])
async def reject_shop(
    shop_id: str, 
    request: RejectRequest, 
    admin: dict = Depends(get_admin_user)
):
    """
    Rejects a shop application and leaves a permanent record.
    The user's global role safely remains 'guest'.
    """
    try:
        shop_ref = db.collection("shops").document(shop_id)
        if not shop_ref.get().exists:
            raise HTTPException(status_code=404, detail="Shop application not found.")
            
        # Change status to 'rejected' to remove it from the pending queue
        shop_ref.update({
            "is_verified": False,
            "status": "rejected",
            "rejection_reason": request.reason,
            "rejected_by": admin.get("email"),
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        
        return {"message": f"Shop {shop_id} application has been rejected."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 📢 LISTING MODERATION ---

@router.put("/listings/{listing_id}/takedown", tags=["Admin - Listings"])
async def takedown_listing(
    listing_id: str, 
    request: TakedownRequest, 
    admin: dict = Depends(get_admin_user)
):
    """Instantly removes an inappropriate listing from the public feeds."""
    try:
        listing_ref = db.collection("listings").document(listing_id)
        if not listing_ref.get().exists:
            raise HTTPException(status_code=404, detail="Listing not found.")
            
        # Change status from 'active' to 'removed' so the GET /live queries ignore it
        listing_ref.update({
            "status": "removed",
            "takedown_reason": request.reason,
            "moderated_by": admin.get("uid"),
            "moderated_at": firestore.SERVER_TIMESTAMP
        })
        
        return {"message": "Listing successfully removed from public feeds."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- 👤 USER MODERATION ---

# 🌟 NEW ENDPOINT: Search User by Email
@router.get("/users/search", tags=["Admin - Users"])
async def search_user_by_email(
    email: str, 
    admin: dict = Depends(get_admin_user)
):
    """
    Allows the Admin to search for a user by email to get their UID.
    Used for promoting admins, banning users, or checking profiles.
    """
    try:
        # Query Firestore for the exact email
        users = db.collection("users").where("email", "==", email).stream()
        
        results = [{"uid": user.id, **user.to_dict()} for user in users]
        
        if not results:
            raise HTTPException(status_code=404, detail="No user found with that email.")
            
        return {"data": results}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{uid}/role", tags=["Admin - Users"])
async def set_user_role(
    uid: str, 
    request: RoleUpdate, 
    admin: dict = Depends(get_admin_user)
):
    """
    Master switchboard to set ANY user's role. 
    Can be used to ban bad actors or promote new admins.
    """
    try:
        valid_roles = ["student", "guest", "shop", "admin", "banned"]
        if request.role not in valid_roles:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid role. Must be one of: {valid_roles}"
            )

        user_ref = db.collection("users").document(uid)
        if not user_ref.get().exists:
            raise HTTPException(status_code=404, detail="User not found.")
            
        user_ref.update({"role": request.role})
        
        return {"message": f"User {uid} role successfully updated to '{request.role}'."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))