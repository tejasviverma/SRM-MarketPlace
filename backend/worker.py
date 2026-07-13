import os
import asyncio
from arq.connections import RedisSettings
import firebase_admin
from firebase_admin import credentials, messaging, firestore

# ==========================================
# 1. SECURE FIREBASE INITIALIZATION
# ==========================================
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ==========================================
# 2. OPTIMIZED BACKGROUND JOB (DATA-ONLY)
# ==========================================
async def process_push_notification(ctx, user_id: str, title: str, body: str, url: str = "/inbox"):
    """Sends a data-only payload via Multicast and cleans up dead tokens."""
    try:
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return False
            
        user_data = user_doc.to_dict()
        # Deduplicate tokens just in case
        tokens = list(set(user_data.get("fcmTokens", [])))
        
        if not tokens:
            return False

        message = messaging.MulticastMessage(
            data={
                "title": str(title),
                "body": str(body),
                "url": str(url)
            },
            tokens=tokens[:500], # Firebase limit per multicast is 500
        )
        
        response = messaging.send_each_for_multicast(message)
        
        # 🚨 SAFE TOKEN CLEANUP
        if response.failure_count > 0:
            failed_tokens = []
            for idx, resp in enumerate(response.responses):
                if not resp.success:
                    error_msg = str(resp.exception)
                    # Only delete the token if Google explicitly says it is permanently dead
                    if "UNREGISTERED" in error_msg or "INVALID_ARGUMENT" in error_msg or "NOT_FOUND" in error_msg:
                        failed_tokens.append(tokens[idx])
            
            if failed_tokens:
                print(f"🗑️ Cleaning up {len(failed_tokens)} dead token(s) for user {user_id}...")
                user_ref.update({"fcmTokens": firestore.ArrayRemove(failed_tokens)})
                
        return True

    except Exception as e:
        print(f"Worker Error [process_push_notification]: {e}")
        return False

# ==========================================
# 3. GLOBAL TOPIC BROADCAST (NEW)
# ==========================================
async def broadcast_new_pool_topic(ctx, pool_id: str, app_name: str, host_name: str, pickup_location: str):
    """Broadcasts a real-time notification to all active devices using FCM Topics."""
    try:
        topic_name = "campus_active_pools"
        
        # Data-only payload to match your Service Worker architecture
        message = messaging.Message(
            topic=topic_name,
            data={
                "type": "new_pool",
                "pool_id": str(pool_id),
                "title": f"🛒 New {app_name} Pool!",
                "body": f"{host_name} started a new order to {pickup_location}.",
                "url": "/" 
            }
        )
        
        response = messaging.send(message)
        print(f"Topic Broadcast successful: {response}")
        return True
        
    except Exception as e:
        print(f"Topic Broadcast Error: {e}")
        return False

# ==========================================
# 4. REDIS CONFIGURATION
# ==========================================
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

class WorkerSettings:
    # Both functions are now safely registered and ready to receive jobs from FastAPI
    functions = [process_push_notification, broadcast_new_pool_topic]
    redis_settings = RedisSettings.from_dsn(redis_url)
    max_jobs = 100