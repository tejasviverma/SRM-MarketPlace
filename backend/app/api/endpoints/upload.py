from fastapi import APIRouter, Depends, HTTPException, Query
from app.core.security import get_current_user
from app.services.storage_service import generate_signed_upload_url

router = APIRouter()

@router.get("/signed-url", tags=["Storage"])
async def get_signed_url(
    content_type: str = Query(..., example="image/jpeg", description="The MIME type of the file"),
    file_extension: str = Query(..., example=".jpg", description="File extension including the dot"),
    user: dict = Depends(get_current_user) # 🛡️ The Bouncer: Only logged-in users can upload
):
    """
    Requests a temporary Google Cloud Storage upload link.
    """
    try:
        # 1. Strict Validation: Prevent users from uploading PDFs or malicious scripts
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Security Error: Only image files are allowed.")
            
        # 2. Generate the URLs using our service
        urls = generate_signed_upload_url(
            file_extension=file_extension, 
            content_type=content_type, 
            user_id=user.get("uid")
        )
        
        return {
            "message": "Upload URL generated successfully.",
            "data": urls
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate upload link: {str(e)}")