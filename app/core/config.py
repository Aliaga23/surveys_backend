from pydantic_settings import BaseSettings
from pydantic import AnyUrl

class Settings(BaseSettings):
    DATABASE_URL: AnyUrl
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    WHAPI_TOKEN: str
    WHAPI_API_URL: str = "https://gate.whapi.cloud"
    OPENAI_API_KEY: str
    class Config:
        env_file = ".env"

settings = Settings()
