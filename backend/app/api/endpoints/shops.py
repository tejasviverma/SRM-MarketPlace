from fastapi import APIRouter, Depends, HTTPException
from google.cloud import firestore

from app.core.firebase import db
from app.core.security import get_current_user, get_marketplace_user, get_verified_shop
from app.models.shop import ShopCreate, CatalogItemCreate

router = APIRouter()

# --- PUBLIC ROUTES (For Students & Shops Browsing) ---

@router.get("/live", tags=["Shops - Public"])
async def get_all_verified_shops(user: dict = Depends(get_marketplace_user)): # 🛡️ SHARED: Students + Shops
    """Allows both students and verified shops to view the business directory."""
    try:
        # 🌟 CHANGED: Now queries by 'status' == 'approved' for production reliability
        shops = db.collection("shops").where("status", "==", "approved").stream()
        return {"data": [{"id": shop.id, **shop.to_dict()} for shop in shops]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{shop_id}/catalog", tags=["Shops - Public"])
async def get_shop_catalog(shop_id: str, user: dict = Depends(get_marketplace_user)): # 🛡️ SHARED: Students + Shops
    """Allows both students and verified shops to view a specific shop's items."""
    try:
        catalog = db.collection("shops").document(shop_id).collection("catalog").stream()
        return {"data": [{"id": item.id, **item.to_dict()} for item in catalog]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- PRIVATE ROUTES (For Shop Owners & Applicants) ---

@router.post("/create", tags=["Shops - Private"])
async def create_shop_profile(
    shop_data: ShopCreate, 
    user: dict = Depends(get_current_user) # 🛡️ BASE: Anyone can apply
):
    """Allows ANY user to apply to create a business profile. Requires Admin approval."""
    try:
        uid = user.get("uid")
        shop_ref = db.collection("shops").document(uid)
        shop_doc = shop_ref.get()
        
        # 🌟 NEW LOGIC: Prevent spam, but allow second chances if rejected!
        if shop_doc.exists:
            current_status = shop_doc.to_dict().get("status", "pending")
            if current_status in ["pending", "approved"]:
                raise HTTPException(
                    status_code=400, 
                    detail=f"You already have a {current_status} shop application."
                )
            # If current_status is "rejected", it skips this error and overwrites their old app!

        # Convert the Pydantic model to a dictionary
        shop_dict = shop_data.model_dump()
        shop_dict["owner_id"] = uid
        shop_dict["owner_email"] = user.get("email") # Good for admin to see who applied
        
        # 🌟 The new production status trackers
        shop_dict["status"] = "pending" 
        shop_dict["is_verified"] = False # Kept for backward compatibility with your doors
        shop_dict["created_at"] = firestore.SERVER_TIMESTAMP
        
        # Using .set() ensures if they were rejected, we completely overwrite the old data
        shop_ref.set(shop_dict)
        
        return {"message": "Shop application submitted! Pending admin approval.", "shop_id": uid}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/catalog/add", tags=["Shops - Private"])
async def add_catalog_item(
    item: CatalogItemCreate, 
    shop_owner: dict = Depends(get_verified_shop) # 🛡️ STRICT: Only verified shops can post
):
    """Allows a verified business to add a permanent item to their shop."""
    try:
        uid = shop_owner.get("uid")
        
        # We assume the shop document ID is the same as the owner's UID for simplicity
        shop_ref = db.collection("shops").document(uid)
        
        # Add to the sub-collection
        new_item_ref = shop_ref.collection("catalog").document()
        new_item_ref.set(item.model_dump())
        
        return {"message": "Item added to catalog successfully", "item_id": new_item_ref.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))