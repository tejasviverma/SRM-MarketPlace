from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_current_user
from app.services.user_service import UserService

router = APIRouter()

# 🆕 Create the Pydantic model to catch frontend input
class SyncRequest(BaseModel):
    selected_role: str  # The frontend will send "student" or "shop"

@router.post("/sync", tags=["User Management"])
async def sync_user_profile(
    payload: SyncRequest, # 🆕 Catch the payload here
    user: dict = Depends(get_current_user)
):
    """
    The frontend should call this route exactly ONCE right after a user logs in.
    It checks if the user exists in Firestore. If not, it creates their profile 
    and assigns them the correct role based on their selection and email domain.
    """
    try:
        uid = user.get("uid")
        email = user.get("email")
        name = user.get("name", email.split("@")[0]) 
        
        # 🆕 Hand the work directly to the Service layer, passing the selected_role
        profile = UserService.sync_user_profile(uid, email, name, payload.selected_role)
        
        # Guide the frontend on what to do next
        next_step = "apply_for_shop" if payload.selected_role == "shop" and profile.get("role") == "guest" else "dashboard"
        
        return {
            "message": "User synchronized", 
            "profile": profile,
            "next_step": next_step
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me", tags=["User Management"])
async def get_my_profile(user: dict = Depends(get_current_user)):
    """
    Fetches the currently logged-in user's profile data.
    """
    try:
        uid = user.get("uid")
        profile = UserService.get_profile(uid)
        return {"profile": profile}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))