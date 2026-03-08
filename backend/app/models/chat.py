from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum




# 2. Define your strict BidStatus rules
class BidStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"   

# 1. The input when a student clicks "Make a Bid"
class BidInitiate(BaseModel):
    listing_id: str
    owner_id: str = Field(..., description="The UID of the person selling the item")
    initial_message: str = Field(..., max_length=500)
    bid_amount: Optional[float] = Field(None, ge=0.0, description="Optional: The price they are offering")
    bid_status: Optional[BidStatus] = None
# 2. What a single message looks like in the database
class ChatMessage(BaseModel):
    sender_id: str
    text: str
    is_bid: bool = False
    bid_amount: Optional[float] = None
    # timestamp will be handled by Firestore SERVER_TIMESTAMP


