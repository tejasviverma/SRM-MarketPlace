from firebase_admin import storage
from datetime import timedelta
import uuid

def generate_signed_upload_url(file_extension: str, content_type: str, user_id: str) -> dict:
    """
    Generates a secure, 5-minute URL that allows the frontend to upload 
    a file directly to Google Cloud Storage.
    """
    # 1. Connect to the Firebase Storage Bucket defined in your .env
    bucket = storage.bucket()
    
    # 2. Generate a unique, collision-proof filename 
    # Example: uploads/user123/a1b2c3d4.jpg
    unique_id = str(uuid.uuid4())
    filename = f"uploads/{user_id}/{unique_id}{file_extension}"
    blob = bucket.blob(filename)
    
    # 3. Create the 5-minute cryptographic gate pass (Signed URL)
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=5),
        method="PUT",
        content_type=content_type
    )
    
    # 4. Mathematically calculate what the public URL WILL be once the frontend finishes uploading
    # We replace the forward slashes with '%2F' because that's how Firebase formats public URLs
    safe_filename = filename.replace("/", "%2F")
    public_url = f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/{safe_filename}?alt=media"
    
    return {
        "upload_url": url,       # Frontend uses this strictly for the PUT request
        "public_url": public_url # Frontend saves this string to the database under 'images: []'
    }