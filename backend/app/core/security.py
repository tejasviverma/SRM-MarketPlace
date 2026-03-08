from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from firebase_admin import auth

from app.core.firebase import db

# This tells FastAPI to look for the "Authorization: Bearer <token>" header
security = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    DOOR 1 (Base): Verifies the Firebase ID token. 
    Lets ANYONE with a valid token in (Gmail, SRM, etc.).
    """
    token = credentials.credentials
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_srm_student(user: dict = Depends(get_current_user)):
    """
    DOOR 2 (Strict): Only allows users with an @srmist.edu.in email.
    """
    email = user.get("email", "")
    
    if not email.endswith("@srmist.edu.in"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You must use an @srmist.edu.in email to access the student marketplace."
        )
    return user


def get_verified_shop(user: dict = Depends(get_current_user)):
    """
    DOOR 3 (Strict): Checks Firestore to ensure this user has the 'shop' role.
    """
    uid = user.get("uid")
    
    # Check the database for the user's official role
    user_doc = db.collection("users").document(uid).get()
    
    if not user_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="User profile not found. Please sync your profile first."
        )
        
    user_data = user_doc.to_dict()
    
    # Check if they have been verified by an Admin
    if user_data.get("role") != "shop":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Access Denied. Your shop account is either pending admin approval or you are registered as a student."
        )
        
    return user


def get_marketplace_user(user: dict = Depends(get_current_user)):
    """
    DOOR 4 (Shared): Allows SRM Students OR Verified Shops to enter.
    Used for viewing the public feeds and directories.
    """
    email = user.get("email", "")
    
    # 1. THE FAST PATH: If they are an SRM student, let them in immediately! (0 DB reads)
    if email.endswith("@srmist.edu.in"):
        return user
        
    # 2. THE SLOW PATH: If they have a Gmail/Yahoo etc., check if they are a verified shop
    uid = user.get("uid")
    user_doc = db.collection("users").document(uid).get()
    
    if user_doc.exists and user_doc.to_dict().get("role") == "shop":
        return user
        
    # 3. KICK OUT: If they are neither, deny access.
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access denied. You must be an SRM student or a verified shop owner to view the marketplace."
    )


def get_admin_user(user: dict = Depends(get_current_user)):
    """
    DOOR 5 (God Mode): Strictly for Super Admins.
    Used for moderating shops, users, and listings.
    """
    uid = user.get("uid")
    user_doc = db.collection("users").document(uid).get()
    
    # Check if the user exists and holds the explicit "admin" role
    if not user_doc.exists or user_doc.to_dict().get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied. You do not have administrator privileges."
        )
        
    return user