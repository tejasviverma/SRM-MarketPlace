from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path

# THIS is the variable that firebase.py is looking for!
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    """Master configuration object."""
    PROJECT_NAME: str = "SRM Campus Economy API"
    ENVIRONMENT: str = "development"

    FRONTEND_URL: str = "http://localhost:3000"
    
    FIREBASE_CREDENTIALS_PATH: str = "serviceAccountKey.json"
    FIREBASE_STORAGE_BUCKET: str 
    SECRET_KEY: str = "8eY1vwLMBtkI0KLwwrQQFMZZLdAMjEdDRThtRu5JOmo"
    SENTRY_DSN: str | None = None

    gmail_address: str
    brevo_api_key: str

    # 🚨 ADDED THIS LINE TO FIX THE PYDANTIC ERROR:
    REDIS_URL: str = "redis://localhost:6379"

    class Config:
        env_file = str(BASE_DIR / ".env") 
        # Optional safeguard: This tells Pydantic to ignore extra variables in the .env instead of crashing
        extra = "ignore" 

@lru_cache()
def get_settings():
    return Settings()

settings = get_settings()