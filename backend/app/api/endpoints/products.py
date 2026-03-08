from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from google.cloud import firestore

from app.core.firebase import db
from app.core.security import get_srm_student, get_marketplace_user
from app.models.listing import ListingCreate, ListingStatus 

router = APIRouter()

@router.get("/live", tags=["Products"])
async def get_live_products(
    category: Optional[str] = Query(None),
    limit: int = Query(15, le=30),
    cursor: Optional[str] = Query(None),
    user: dict = Depends(get_marketplace_user) # 🛡️ SHARED DOOR: Both students and shops can view!
):
    try:
        query = db.collection("listings").where("status", "==", "active").order_by("created_at", direction=firestore.Query.DESCENDING)
        
        if category:
            query = query.where("category", "==", category)
            
        if cursor:
            cursor_doc = db.collection("listings").document(cursor).get()
            if cursor_doc.exists:
                query = query.start_after(cursor_doc)
                
        docs = query.limit(limit).stream()
        
        results = []
        last_doc_id = None
        
        for doc in docs:
            item = doc.to_dict()
            item["id"] = doc.id
            results.append(item)
            last_doc_id = doc.id
            
        return {
            "data": results,
            "next_cursor": last_doc_id,
            "count": len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch feed: {str(e)}")


@router.post("/create", response_model=dict, tags=["Products"])
async def create_product(
    listing: ListingCreate, 
    user: dict = Depends(get_srm_student) # 🛡️ STRICT DOOR: Only students can post here
):
    try:
        listing_data = listing.model_dump()
        listing_data["owner_id"] = user.get("uid")
        listing_data["status"] = ListingStatus.ACTIVE
        listing_data["created_at"] = firestore.SERVER_TIMESTAMP 
        
        doc_ref = db.collection("listings").document() 
        doc_ref.set(listing_data)
        
        return {"message": "Ad posted successfully!", "id": doc_ref.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to post ad: {str(e)}")