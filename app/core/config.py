from pydantic_settings import BaseSettings
from pydantic import AnyUrl
import os

class Settings(BaseSettings):
    DATABASE_URL: AnyUrl
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    WHAPI_TOKEN: str
    WHAPI_API_URL: str = "https://gate.whapi.cloud"
    OPENAI_API_KEY: str
    VAPI_API_URL: str 
    VAPI_API_KEY: str
    API_BASE_URL: str 
    VAPI_PHONE_NUMBER_ID: str
    VAPI_ASSISTANT_ID: str
    STRIPE_SECRET_KEY: str
    STRIPE_PUBLIC_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    SURVEY_LINK_EXPIRY_DAYS: int 
    SMTP_SERVER: str 
    SMTP_PORT: int 
    SMTP_USERNAME: str 
    SMTP_PASSWORD: str 
    
    class Config:
        env_file = ".env"

settings = Settings()
