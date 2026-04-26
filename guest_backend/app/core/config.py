"""
Core configuration settings for the guest-side backend.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # MongoDB Configuration
    MONGODB_URL: str = "mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority"
    MONGODB_DB_NAME: str = "emergency_db"
    
    # Staff Backend Integration
    STAFF_BACKEND_URL: str = "http://localhost:8001"
    STAFF_BACKEND_TIMEOUT: int = 10  # seconds
    
    # Application Settings
    APP_NAME: str = "Smart Emergency Management - Guest Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Session Configuration
    SESSION_TIMEOUT_MINUTES: int = 60
    
    # Navigation Configuration
    PATHFINDING_ALGORITHM: str = "dijkstra"  # or "bfs"

    # JWT Authentication
    # Must match the staff backend secret — same DB, shared token validation.
    # Generate with: python -c "import secrets; print(secrets.token_hex(64))"
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES_STAFF: int = 20
    ACCESS_TOKEN_EXPIRE_MINUTES_GUEST: int = 10
    REFRESH_TOKEN_EXPIRE_HOURS: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
